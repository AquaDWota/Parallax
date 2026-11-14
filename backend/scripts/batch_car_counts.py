"""Batch job: real car counts per building per Vexcel collection. RUN ON YOUR LAPTOP.

Two ways to give it buildings:

  # 1. a CSV with building_id,lat,lon[,name,city]  (e.g. exported from CoStar)
  python -m scripts.batch_car_counts --buildings ../data/real/costar_buildings.csv

  # 2. discover large buildings around a point (no CoStar needed) - good for the demo map
  python -m scripts.batch_car_counts --discover 29.7274,-95.5616 --radius 700 --city Houston --area Westchase
  python -m scripts.batch_car_counts --discover 33.9197,-118.3963 --radius 700 --city "Los Angeles" --area "El Segundo"

Writes (appends, safe to stop and re-run - finished buildings are skipped):
  data/real/vexcel_buildings.csv   building_id,name,city,area,lat,lon,lot_area_m2,hardscape_m2,footprint_m2,stall_capacity_est,lot_wkt
  data/real/captures.csv           capture_id,city,capture_date,first_capture,last_capture,holiday
  data/real/car_counts.csv         building_id,capture_id,cars,quality_flag,mean_conf

What the probe taught us (built in here):
  * ~1 collection a year 2016/17-2026, from overlapping campaigns -> capture_id = collection name
  * test / oblique-only collections (sanborn, graydata, t-*) have no ortho -> skipped by name
  * captures flown Dec 15 - Jan 5 or Thanksgiving week are flagged holiday=1 (lots look empty)
  * Detection runs on the lot = parcel minus building footprints
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from shapely import wkt as swkt
from shapely.geometry import shape

from parallax.config import DATA_DIR
from parallax.vexcel import VexcelClient, lot_polygon, square_around

OUT = DATA_DIR / "real"
OUT.mkdir(parents=True, exist_ok=True)
F_BLD, F_CAP, F_CC = OUT / "vexcel_buildings.csv", OUT / "captures.csv", OUT / "car_counts.csv"
BLD_COLS = ["building_id", "name", "city", "area", "lat", "lon", "lot_area_m2", "hardscape_m2",
            "footprint_m2", "stall_capacity_est", "lot_wkt"]
CAP_COLS = ["capture_id", "city", "capture_date", "first_capture", "last_capture", "holiday"]
CC_COLS = ["building_id", "capture_id", "cars", "quality_flag", "mean_conf"]
ORTHO_NAME = re.compile(r"^(us-[a-z]{2}-|[ns]\d{2}[ew]\d{2,3}-)")
SQM_PER_STALL = 30.0
PRECHECK = True
PRECHECK_MIN_CARS = 5
lock = threading.Lock()


def m2(geom, lat: float) -> float:
    """Approximate area in m^2 of a lon/lat geometry."""
    return geom.area * (111_320 ** 2) * math.cos(math.radians(lat))


def holiday(first: str, last: str) -> int:
    try:
        a = datetime.fromisoformat(first[:10])
        b = datetime.fromisoformat(last[:10])
    except ValueError:
        return 0
    mid = a + (b - a) / 2
    md = (mid.month, mid.day)
    return int(md >= (12, 15) or md <= (1, 5) or (mid.month == 11 and 22 <= mid.day <= 30))


def _append(path, cols, rows):
    with lock:
        new = not path.exists()
        with open(path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            if new:
                w.writeheader()
            w.writerows(rows)


def _read(path):
    if not path.exists():
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def discover(c: VexcelClient, lat: float, lon: float, radius: float, min_sqft: float, limit: int) -> list[dict]:
    """Parcels with big buildings around a point (commercial heuristic: footprint >= min_sqft)."""
    area = square_around(lat, lon, radius)
    out, page = [], 1
    while len(out) < limit:
        r = c.send("GET", "property/extract", timeout=180, params={
            "wkt": area, "srid": 4326, "layer": "urban,urban-r,wide-area,urban-g", "latest": "true",
            "include": "precomputed", "unit-system": "imperial", "page": page, "page-size": 200})
        if r.status_code == 404:
            break
        r.raise_for_status()
        feats = r.json().get("features", [])
        if not feats:
            break
        for f in feats:
            s = f["properties"].get("structures", [])
            fp = sum(x.get("footprint.area") or 0 for x in s)
            if fp >= min_sqft:
                g = f["geometry"]
                geom = swkt.loads(g) if isinstance(g, str) else shape(g)
                pt = geom.representative_point()
                out.append({"lat": pt.y, "lon": pt.x, "parcel": f})
        if len(feats) < 200:
            break
        page += 1
    return out[:limit]


def process(c: VexcelClient, b: dict, known_caps: set) -> tuple[int, int]:
    lat, lon = float(b["lat"]), float(b["lon"])
    feat = b.get("parcel")
    if feat is None:
        prop = c.parcel(lat, lon)
        feat = prop["features"][0] if prop and prop.get("features") else None
    if feat is not None:
        a = feat["properties"]
        lot = swkt.loads(lot_polygon(feat))
        fp_sqft = sum(x.get("footprint.area") or 0 for x in a.get("structures", []))
        hard = a.get("hardscapes.area")
    else:
        lot, fp_sqft, hard = swkt.loads(square_around(lat, lon, 60)), 0, None
    lot_m2 = m2(lot, lat)
    hard_m2 = (float(hard) * 0.0929) if hard else None  # imperial sq ft -> m^2
    cap_area = min(hard_m2, lot_m2) if hard_m2 else lot_m2 * 0.7
    capacity = max(10, int(cap_area / SQM_PER_STALL))
    _append(F_BLD, BLD_COLS, [dict(building_id=b["building_id"], name=b.get("name", ""), city=b["city"],
                                   area=b.get("area", ""), lat=round(lat, 6), lon=round(lon, 6),
                                   lot_area_m2=round(lot_m2), hardscape_m2=round(hard_m2) if hard_m2 else "",
                                   footprint_m2=round(fp_sqft * 0.0929), stall_capacity_est=capacity,
                                   lot_wkt=lot.wkt)])

    cols = {}
    for pt in ("oblique", "nadir"):
        try:
            for x in c.list_collections(lot.wkt, pt):
                n = x.get("collection")
                if n and ORTHO_NAME.match(n) and n not in cols:
                    cols[n] = x
        except Exception:
            pass
    caps, rows = [], []
    ordered = sorted(cols.items(), key=lambda kv: kv[1].get("first-capture-date", ""))
    # Pre-check on the newest capture: a lot with almost no cars is a garage building or a
    # mis-placed lot. Skip its other captures to save ~10 API calls per building.
    skip_rest = False
    if PRECHECK and ordered:
        try:
            newest = ordered[-1][0]
            if c.detect_cars(lot.wkt, collection=newest)["count"] < PRECHECK_MIN_CARS:
                skip_rest = True
        except Exception:
            pass
    for n, x in ordered:
        first, last = x.get("first-capture-date", ""), x.get("last-capture-date", "")
        if (b["city"], n) not in known_caps:
            mid = ""
            try:
                a_, b_ = datetime.fromisoformat(first[:19]), datetime.fromisoformat(last[:19])
                mid = (a_ + (b_ - a_) / 2).date().isoformat()
            except ValueError:
                mid = first[:10]
            caps.append(dict(capture_id=n, city=b["city"], capture_date=mid, first_capture=first[:10],
                             last_capture=last[:10], holiday=holiday(first, last)))
            known_caps.add((b["city"], n))
        if skip_rest:
            rows.append(dict(building_id=b["building_id"], capture_id=n, cars="",
                             quality_flag="not_measurable", mean_conf=""))
            continue
        try:
            d = c.detect_cars(lot.wkt, collection=n)
            conf = [z["confidence"] or 0 for z in d["detections"]]
            rows.append(dict(building_id=b["building_id"], capture_id=n, cars=d["count"],
                             quality_flag="ok", mean_conf=round(sum(conf) / len(conf), 3) if conf else ""))
        except Exception as e:
            rows.append(dict(building_id=b["building_id"], capture_id=n, cars="",
                             quality_flag="no_image" if "404" in str(e) else "error", mean_conf=""))
    _append(F_CAP, CAP_COLS, caps)
    _append(F_CC, CC_COLS, rows)
    return len(rows), sum(1 for r in rows if r["quality_flag"] == "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buildings", help="CSV with building_id,lat,lon[,name,city]")
    ap.add_argument("--discover", help="lat,lon to search around")
    ap.add_argument("--radius", type=float, default=700, help="metres, centre to edge")
    ap.add_argument("--city", default="Houston")
    ap.add_argument("--area", default="", help="label, e.g. Westchase (used as submarket)")
    ap.add_argument("--min-sqft", type=float, default=15000, help="discover: min building footprint")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--workers", type=int, default=3, help="parallel buildings (watch for 429s)")
    ap.add_argument("--no-precheck", action="store_true", help="count every capture even if the newest lot is empty")
    a = ap.parse_args()
    global PRECHECK
    PRECHECK = not a.no_precheck

    c = VexcelClient()
    if a.buildings:
        with open(a.buildings, newline="") as fh:
            todo = [dict(r, city=r.get("city") or a.city, area=r.get("area") or a.area) for r in csv.DictReader(fh)][: a.limit]
    elif a.discover:
        lat, lon = map(float, a.discover.split(","))
        print(f"discovering buildings >= {a.min_sqft:,.0f} sq ft within {a.radius} m of {lat},{lon} ...")
        found = discover(c, lat, lon, a.radius, a.min_sqft, a.limit)
        tag = re.sub(r"\W+", "", (a.area or a.city))[:6].upper()
        todo = [dict(building_id=f"V-{tag}-{i:03d}", name="", city=a.city, area=a.area, **f) for i, f in enumerate(found)]
        print(f"found {len(todo)} buildings")
    else:
        ap.error("give --buildings or --discover")

    done = {r["building_id"] for r in _read(F_CC)}
    known = {(r["city"], r["capture_id"]) for r in _read(F_CAP)}
    todo = [b for b in todo if b["building_id"] not in done]
    print(f"{len(todo)} buildings to process ({len(done)} already done), {a.workers} at a time")
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process, c, b, known): b for b in todo}
        for i, f in enumerate(as_completed(futs), 1):
            b = futs[f]
            try:
                n, ok = f.result()
                tag = "  (empty lot / garage - skipped)" if n and not ok else ""
                print(f"[{i}/{len(todo)}] {b['building_id']} {b.get('name', '')}: {ok}/{n} collections counted{tag}  ({time.time() - t0:.0f}s)")
            except Exception as e:
                print(f"[{i}/{len(todo)}] {b['building_id']}: FAILED {str(e)[:160]}")
    print(f"\nDone. Files in {OUT}. Tell Claude when it's finished.")


if __name__ == "__main__":
    sys.exit(main())
