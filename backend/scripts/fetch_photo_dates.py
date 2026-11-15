"""Exact day each Vexcel photo of a building was taken -> data/real/photo_dates.csv

Vexcel collections only carry a date *range* (often weeks), but `oriented/query` lists every raw photo
over a point with its own capture timestamp. For each (building, collection) we keep the local dates
of the photos (nadir ones when the collection has them - the ortho we count cars on is built from
those). The loader turns the dates into a day type with parallax.photo_days (workday / saturday /
sunday / holiday / mixed / unknown), so the calendar rules can change without re-fetching.

Run (needs VEXCEL_API_KEY; ~5 min, resumable):
  python -m scripts.fetch_photo_dates            # all buildings in vexcel_buildings.csv
  python -m scripts.fetch_photo_dates --limit 5  # quick test
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from parallax.loaders import REAL_DIR
from parallax.photo_days import classify
from parallax.vexcel import VexcelClient

OUT = REAL_DIR / "photo_dates.csv"
COLS = ["building_id", "capture_id", "dates", "day_type", "n_photos", "source"]
TZ = {"Houston": ZoneInfo("America/Chicago"), "Los Angeles": ZoneInfo("America/Los_Angeles")}


def local_date(ts: str, tz: ZoneInfo) -> date:
    # Vexcel capture-date is UTC without an offset, e.g. "2025-12-31T18:11:50" (= 12:11 in Houston)
    return datetime.fromisoformat(ts[:19]).replace(tzinfo=timezone.utc).astimezone(tz).date()


def fetch(client: VexcelClient, b) -> list[dict]:
    r = client.send("GET", "oriented/query", timeout=120, params={
        "wkt": f"POINT ({b.lon} {b.lat})", "srid": 4326, "include": "collection,capture-date,product-type"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    tz = TZ.get(b.city, TZ["Houston"])
    nadir, every = defaultdict(set), defaultdict(set)
    for f in r.json().get("features", []):
        p = f["properties"]
        if not p.get("capture-date") or not p.get("collection"):
            continue
        d = local_date(p["capture-date"], tz)
        every[p["collection"]].add(d)
        if p.get("product-type") == "nadir":
            nadir[p["collection"]].add(d)
    rows = []
    for col, ds in every.items():
        use, src = (nadir[col], "nadir") if nadir.get(col) else (ds, "all")
        rows.append(dict(building_id=b.building_id, capture_id=col, dates=";".join(d.isoformat() for d in sorted(use)),
                         day_type=classify(sorted(use)), n_photos=len(use), source=src))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    vb = pd.read_csv(REAL_DIR / "vexcel_buildings.csv").drop_duplicates("building_id", keep="last")
    counted = pd.read_csv(REAL_DIR / "car_counts.csv")[["building_id", "capture_id"]].drop_duplicates()
    done = set(pd.read_csv(OUT).building_id) if OUT.exists() else set()
    todo = vb[~vb.building_id.isin(done) & vb.lat.notna()]
    if a.limit:
        todo = todo.head(a.limit)
    print(f"{len(done)} buildings already done, fetching {len(todo)}", file=sys.stderr)

    client = VexcelClient()
    new_file = not OUT.exists()
    with OUT.open("a", newline="") as fh, ThreadPoolExecutor(a.workers) as pool:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new_file:
            w.writeheader()
        futs = {pool.submit(fetch, client, b): b.building_id for b in todo.itertuples()}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rows = fut.result()
            except Exception as e:  # noqa: BLE001 - keep going, rerun picks it up
                print(f"  {futs[fut]}: {e}", file=sys.stderr)
                continue
            w.writerows(rows)
            fh.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}", file=sys.stderr)

    pdts = pd.read_csv(OUT).drop_duplicates(["building_id", "capture_id"], keep="last")
    m = counted.merge(pdts, on=["building_id", "capture_id"], how="left")
    print(f"\n{len(m)} counted (building, flight) pairs; day type:", file=sys.stderr)
    print(m.day_type.fillna("unknown").value_counts().to_string(), file=sys.stderr)


if __name__ == "__main__":
    main()
