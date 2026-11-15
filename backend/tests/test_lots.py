"""Lot outlines: clipping to parcels drops streets (offline, geometry only)."""
from shapely.geometry import box, mapping

from parallax.lots import clip_to_parcels

LAT, LON = 29.73, -95.56
M = 1 / 111_320          # ~1 m in degrees of latitude (close enough at this scale)


def parcel(x0, y0, x1, y1):
    return {"geometry": mapping(box(LON + x0 * M, LAT + y0 * M, LON + x1 * M, LAT + y1 * M))}


def test_street_between_two_parcels_is_removed():
    lot = box(LON, LAT, LON + 100 * M, LAT + 60 * M)
    feats = [parcel(0, 0, 45, 60), parcel(55, 0, 100, 60)]          # a 10 m street at x = 45..55
    new, kept = clip_to_parcels(lot, feats)
    assert kept is not None and 0.85 < kept < 0.95
    assert not new.contains(box(LON + 48 * M, LAT + 10 * M, LON + 52 * M, LAT + 50 * M).centroid)
    assert new.contains(box(LON + 10 * M, LAT + 10 * M, LON + 20 * M, LAT + 20 * M).centroid)


def test_missing_parcel_data_leaves_lot_unchanged():
    lot = box(LON, LAT, LON + 100 * M, LAT + 60 * M)
    assert clip_to_parcels(lot, []) == (lot, None)


def test_lot_that_is_mostly_street_reports_a_small_share():
    lot = box(LON, LAT, LON + 100 * M, LAT + 60 * M)
    new, kept = clip_to_parcels(lot, [parcel(0, 0, 10, 10)])
    assert kept is not None and kept < 0.3     # the batch marks such a building not measurable


def test_slivers_along_parcel_edges_are_dropped():
    lot = box(LON, LAT, LON + 100 * M, LAT + 60 * M)
    feats = [parcel(0, 0, 90, 60), parcel(99, 0, 100, 3)]           # a 1 m x 3 m sliver past a road
    new, kept = clip_to_parcels(lot, feats)
    assert new.geom_type == "Polygon" and kept is not None
