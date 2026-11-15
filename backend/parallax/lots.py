"""Where to count cars for a building.

v1 used the building's own parcel minus its footprint. That is often just a strip around the walls:
in office and industrial parks the parking sits on a separate parcel or a shared lot next door.

v2 (this module): a ring around the building footprint, grown outward until it is large enough to
hold the building's surface stalls (CoStar `surface_spaces` x 30 m^2, +30% for aisles), between
MIN_RING_M and MAX_RING_M. The building's own parcel is included unless it is far larger than the ring (a whole business park). Buildings without a stall
count get DEFAULT_RING_M. The ring can take in a neighbour's or street cars; for the study that is
fine as long as the area is the same at every capture (building fixed effects absorb the level).
"""
from __future__ import annotations

import math

from shapely import wkt as swkt
from shapely.geometry import shape
from shapely.ops import transform, unary_union

SQM_PER_STALL = 30.0
AISLE_FACTOR = 1.3
MIN_RING_M, MAX_RING_M, DEFAULT_RING_M = 15.0, 100.0, 40.0


def _to_m(lat0: float):
    k = 111_320.0
    c = math.cos(math.radians(lat0))
    return (lambda x, y, z=None: (x * k * c, y * k)), (lambda x, y, z=None: (x / (k * c), y / k))


def _geom(g):
    return swkt.loads(g) if isinstance(g, str) else shape(g)


def footprints(parcel_feature: dict):
    fps = []
    for s in parcel_feature["properties"].get("structures", []) or []:
        fp = s.get("footprint.wkt") or s.get("footprint-wkt")
        if fp:
            fps.append(swkt.loads(fp))
    return unary_union(fps) if fps else None


def lot_polygon_v2(parcel_feature: dict | None, lat: float, lon: float, surface_spaces: float | None):
    """Return (lot_geometry_lonlat, ring_m, lot_area_m2)."""
    fwd, back = _to_m(lat)
    parcel = _geom(parcel_feature["geometry"]) if parcel_feature else None
    fp = footprints(parcel_feature) if parcel_feature else None
    if fp is None:  # no footprint: treat a 25 m disc at the point (or the parcel centre) as the building
        from shapely.geometry import Point
        centre = parcel.representative_point() if parcel is not None else Point(lon, lat)
        fp = transform(back, transform(fwd, centre).buffer(25))
    fp_m = transform(fwd, fp)
    parcel_m = transform(fwd, parcel) if parcel is not None else None

    target = None
    if surface_spaces is not None and surface_spaces == surface_spaces and surface_spaces >= 10:
        target = float(surface_spaces) * SQM_PER_STALL * AISLE_FACTOR

    def ring(r):
        area = fp_m.buffer(r, join_style=2)
        # include the building's own parcel only when it's the building's own lot, not a whole business park
        if parcel_m is not None and parcel_m.area <= 2.5 * area.area:
            area = area.union(parcel_m)
        return area.difference(fp_m)

    if target is None:
        r = DEFAULT_RING_M
        lot = ring(r)
    else:
        r = MIN_RING_M
        lot = ring(r)
        while lot.area < target and r < MAX_RING_M:
            r += 5.0
            lot = ring(r)
    lot = lot.buffer(0)
    return transform(back, lot), r, lot.area


def subtract_all_footprints(lot, parcel_features: list):
    """Cut every building footprint inside the area out of the lot (lon/lat geometries). Without this a
    neighbour's roof inside the ring gets counted as lot, and AC units / roof shadows become false 'cars'."""
    fps = []
    for f in parcel_features or []:
        for st in f.get("properties", {}).get("structures", []) or []:
            w = st.get("footprint.wkt") or st.get("footprint-wkt")
            if w:
                g = swkt.loads(w)
                if g.intersects(lot):
                    fps.append(g.buffer(0))
    if not fps:
        return lot, 0
    return lot.difference(unary_union(fps)).buffer(0), len(fps)


def clip_to_parcels(lot, parcel_features: list, min_part_m2: float = 25.0):
    """Keep only the parts of the lot that fall inside some parcel. Streets are public right-of-way and belong
    to no parcel, so this drops roads (and the passing / street-parked cars on them) while keeping parking on
    neighbouring parcels. Slivers smaller than `min_part_m2` (about two stalls) are dropped.
    Returns (lot, kept_share). With no parcel data at all the lot comes back unchanged and kept_share is None.
    A small kept_share (say under 0.3) means the 'lot' was mostly street: callers treat that building as having
    no measurable surface lot rather than keep the street outline."""
    from shapely.ops import transform

    parcels = []
    for f in parcel_features or []:
        g = f.get("geometry")
        if g:
            try:
                parcels.append(_geom(g).buffer(0))
            except Exception:
                continue
    if not parcels or lot.is_empty:
        return lot, None
    to_m = _to_m(lot.centroid.y)[0]
    clipped = lot.intersection(unary_union(parcels)).buffer(0)
    parts = [g for g in getattr(clipped, "geoms", [clipped]) if g.geom_type == "Polygon" and transform(to_m, g).area >= min_part_m2]
    if not parts:
        return lot, 0.0
    clipped = unary_union(parts)
    share = transform(to_m, clipped).area / max(transform(to_m, lot).area, 1e-9)
    return clipped, round(share, 3)
