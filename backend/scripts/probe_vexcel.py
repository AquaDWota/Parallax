"""Probe the Vexcel API for one building, end to end. RUN THIS ON YOUR LAPTOP
(the API isn't reachable from Claude's sandbox).

    cd backend
    pip install -r requirements.txt
    # put VEXCEL_API_KEY=... in ../.env  (or export it in this terminal)
    python -m scripts.probe_vexcel                       # 4 default suburban office parks
    python -m scripts.probe_vexcel --lat 29.7823 --lon -95.6355 --name my_bldg

It answers the questions that decide the project:
  1. Is there a parcel + footprint here?          -> lot polygon (parcel minus buildings)
  2. How many historical collections cover it?    -> can we get 2018-2026, two a year?
  3. Can /elements/detect count cars per collection? -> the usage time series
Everything lands in ../vexcel_output/<name>/ (git-ignored). Zip that folder and send it to Claude.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from pathlib import Path

from parallax.config import REPO_ROOT
from parallax.vexcel import VexcelClient, lot_polygon, point, square_around

DEFAULTS = [  # suburban office / retail with big surface lots - adjust freely
    ("houston_energy_corridor", 29.7836, -95.6354),
    ("houston_westchase", 29.7274, -95.5616),
    ("la_el_segundo", 33.9197, -118.3963),
    ("la_woodland_hills", 34.1716, -118.6062),
]


def probe(c: VexcelClient, name: str, lat: float, lon: float, max_collections: int = 20) -> dict:
    out = REPO_ROOT / "vexcel_output" / name
    out.mkdir(parents=True, exist_ok=True)
    rep: dict = {"name": name, "lat": lat, "lon": lon}
    print(f"\n=== {name} ({lat}, {lon}) ===")

    # 1. parcel
    prop = c.parcel(lat, lon)
    if prop and prop.get("features"):
        f = prop["features"][0]
        (out / "property.json").write_text(json.dumps(prop, indent=2))
        a = f["properties"]
        rep["building_type"] = a.get("building-type.class")
        rep["structures"] = a.get("structure.count")
        rep["collection_latest"] = a.get("metadata.collection")
        try:
            area = lot_polygon(f)
        except Exception:
            area = f["geometry"] if isinstance(f["geometry"], str) else None
        area = area or square_around(lat, lon, 80)
        print(f" parcel: type={rep['building_type']} structures={rep['structures']} latest={rep['collection_latest']}")
    else:
        area = square_around(lat, lon, 80)
        print(" no parcel at this point (404) - using a 160 m square")
    rep["area_wkt"] = area

    # 2. history
    cols = []
    for pt in ("oblique", "nadir"):
        try:
            cols += [dict(x, source=f"collections/{pt}") for x in c.list_collections(area, pt)]
        except Exception as e:
            print(f" collections({pt}) failed: {e}")
    try:
        imgs = c.query_images(point(lat, lon), "nadir")
        (out / "oriented_query.json").write_text(json.dumps(imgs, indent=2))
        for i in imgs:
            cols.append({"collection": i.get("collection"), "capture-date": i.get("capture-date"), "source": "oriented/query"})
    except Exception as e:
        print(f" oriented/query failed: {e}")
    (out / "collections.json").write_text(json.dumps(cols, indent=2))
    names = sorted({x.get("collection") for x in cols if x.get("collection")})
    rep["collections"] = names
    print(f" collections covering this spot: {len(names)}")
    for n in names:
        print("   -", n)

    # 3. car counts per collection (+ latest)
    rows = []
    for col in ([None] + names)[: max_collections + 1]:
        label = col or "latest"
        try:
            d = c.detect_cars(area, collection=col)
            img = c.ortho(area, collection=col)
            (out / f"ortho_{label}.jpg").write_bytes(img)
            rows.append({"collection": label, "cars": d["count"],
                         "mean_conf": round(sum(x["confidence"] or 0 for x in d["detections"]) / max(d["count"], 1), 3)})
            print(f" {label:40s} cars={d['count']}")
        except Exception as e:
            rows.append({"collection": label, "cars": None, "error": str(e)[:300]})
            print(f" {label:40s} FAILED: {str(e)[:150]}")
    with open(out / "car_counts.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["collection", "cars", "mean_conf", "error"])
        w.writeheader()
        w.writerows(rows)
    rep["car_counts"] = rows
    (out / "summary.json").write_text(json.dumps(rep, indent=2))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--name", default="custom")
    ap.add_argument("--max-collections", type=int, default=20)
    a = ap.parse_args()
    c = VexcelClient()
    targets = [(a.name, a.lat, a.lon)] if a.lat is not None else DEFAULTS
    reports = []
    for name, lat, lon in targets:
        try:
            reports.append(probe(c, name, lat, lon, a.max_collections))
        except Exception:
            traceback.print_exc()
    (REPO_ROOT / "vexcel_output" / "all_summaries.json").write_text(json.dumps(reports, indent=2))
    print("\nDone. Send Claude the vexcel_output/ folder (zip it).")
    print("Key answers:")
    for r in reports:
        ok = [x for x in r.get("car_counts", []) if x.get("cars") is not None]
        print(f" {r['name']}: {len(r.get('collections', []))} collections, car counts worked for {len(ok)}")


if __name__ == "__main__":
    sys.exit(main())
