"""Prefetch real Vexcel lot images for the demo. RUN ON YOUR LAPTOP (real mode, key in .env).

    python -m scripts.fetch_images                 # every measurable CoStar building, every usable capture
    python -m scripts.fetch_images --boxes         # also draw a box on every detected car (1 extra call each)
    python -m scripts.fetch_images --building P240089 --boxes

Images go to data/imagery/<building_id>/<capture_id>[_boxes].jpg (git-ignored). Safe to stop and re-run:
images already on disk are skipped. One API call per image (two with --boxes).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault("PARALLAX_DATA_MODE", "real")

from parallax import imagery  # noqa: E402
from parallax.store import get_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", action="store_true", help="draw detected cars (extra detect call per image)")
    ap.add_argument("--building", help="only this building id")
    ap.add_argument("--all-buildings", action="store_true", help="include discovered neighbours (V-...)")
    ap.add_argument("--limit", type=int, default=0, help="max buildings (0 = all)")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    u = get_store().usage
    u = u[u.cars.notna() & u.status.isin(["ok", "low_baseline", "no_baseline"])]
    if a.building:
        u = u[u.building_id == a.building]
    elif not a.all_buildings:
        u = u[u.building_id.str.startswith("P")]
    # buildings with a usable index first: those are the ones the demo opens
    order = (u.assign(ok=u.status.eq("ok")).groupby("building_id").ok.sum().sort_values(ascending=False))
    bids = list(order.index[: a.limit] if a.limit else order.index)
    jobs = [(r.building_id, r.capture_id) for r in u[u.building_id.isin(bids)].itertuples()
            if not imagery.cache_path(r.building_id, r.capture_id, a.boxes).exists()]
    print(f"{len(bids)} buildings, {len(jobs)} images to fetch{' with car boxes' if a.boxes else ''}")
    t0, ok = time.time(), 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(imagery.fetch, b, c, a.boxes): (b, c) for b, c in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            b, c = futs[f]
            res = f.result()
            ok += res is not None
            if i % 10 == 0 or res is None:
                print(f"[{i}/{len(jobs)}] {b} {c}: {'ok' if res else 'failed'}  ({time.time() - t0:.0f}s)")
    print(f"\nDone: {ok}/{len(jobs)} images in {imagery.IMG_DIR}")


if __name__ == "__main__":
    sys.exit(main())
