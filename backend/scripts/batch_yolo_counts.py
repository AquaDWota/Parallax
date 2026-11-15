"""Count cars per building per Vexcel collection with the open-source YOLO detector. RUN ON YOUR LAPTOP.

    pip install -r requirements.txt            # adds ultralytics + pillow
    python -m scripts.batch_yolo_counts --limit 50
    python -m scripts.batch_yolo_counts --building P239920 --building P240089
    python -m scripts.batch_yolo_counts --workers 3          # all buildings in car_counts.csv

Reuses the lot polygons (data/real/vexcel_buildings.csv) and the building x collection pairs that the sam3
batch counted (data/real/car_counts.csv), so the two detectors are compared on identical lots and captures.
Pairs sam3 skipped as garages ("not_measurable") are left out unless --all-pairs.

Per pair: split the lot's bounding box into tiles on a fixed grid (default 60 m), fetch each tile's plain
ortho at native resolution (no drawing; PNG, lossless) and cache it under data/imagery_tiles/ - neighbouring lots share
tiles and a re-run makes no new API calls - resample to PARALLAX_YOLO_GSD_M, detect, map boxes to lon/lat,
keep cars inside the lot, drop duplicates on tile edges.

Writes data/real/car_counts_yolo.csv: building_id, capture_id, cars, quality_flag, mean_conf, detector,
model_version. Resumable: pairs already counted with the same model_version are skipped; later rows win.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from shapely import wkt as swkt
from shapely.geometry import box

OUT_COLS = ["building_id", "capture_id", "cars", "quality_flag", "mean_conf", "detector", "model_version"]
_write_lock = threading.Lock()


# ---------------------------------------------------------------- tiles on a fixed grid
def grid_tiles(lot, tile_m: float) -> list[tuple[str, tuple]]:
    """Tiles of a fixed lon/lat grid (one grid per 1-degree latitude band) that touch the lot.
    Returns [(key, (min_lon, min_lat, max_lon, max_lat))]; the key names the cached file."""
    x0, y0, x1, y1 = lot.bounds
    band = math.floor((y0 + y1) / 2)
    dlat = tile_m / 111_320.0
    dlon = tile_m / (111_320.0 * math.cos(math.radians(band + 0.5)))
    out = []
    for ix in range(math.floor(x0 / dlon), math.floor(x1 / dlon) + 1):
        for iy in range(math.floor(y0 / dlat), math.floor(y1 / dlat) + 1):
            b = (ix * dlon, iy * dlat, (ix + 1) * dlon, (iy + 1) * dlat)
            if box(*b).intersects(lot):
                out.append((f"t{int(tile_m)}_b{band}_{ix}_{iy}", b))
    return out


IMAGE_FORMAT = __import__("os").environ.get("PARALLAX_YOLO_IMAGE_FORMAT", "png")


def fetch_tile(client, cache_dir: Path, collection: str, key: str, bounds: tuple) -> bytes | None:
    """Plain ortho of one tile, cached. PNG by default: small cars (10-15 px) vanish under JPEG compression
    (a test crop went from 33 cars to 4 when re-saved at JPEG quality 75). Falls back to JPEG if the API
    refuses PNG. A tile with no image is cached as an empty .none marker."""
    d = cache_dir / collection
    for ext in ("png", "jpg"):
        if (d / f"{key}.{ext}").exists():
            return (d / f"{key}.{ext}").read_bytes()
    if (d / f"{key}.none").exists():
        return None
    d.mkdir(parents=True, exist_ok=True)
    formats = [IMAGE_FORMAT] + (["jpeg"] if IMAGE_FORMAT != "jpeg" else [])
    for i, fmt in enumerate(formats):
        try:
            img, _ = client.ortho_with_size(box(*bounds).wkt, collection=collection, image_format=fmt)
        except RuntimeError as e:
            if "404" in str(e):
                (d / f"{key}.none").touch()
                return None
            if "(400)" in str(e) and i + 1 < len(formats):
                continue  # this format refused: try the next
            raise
        (d / f"{key}.{'jpg' if fmt == 'jpeg' else fmt}").write_bytes(img)
        return img
    return None


def count_pair(client, detector, cache_dir: Path, lot, collection: str, tile_m: float) -> dict:
    """YOLO count for one building x collection. Returns {cars, quality_flag, mean_conf, detections}."""
    from parallax.yolo import dedupe, in_lot

    cars, n_img = [], 0
    for key, b in grid_tiles(lot, tile_m):
        img = fetch_tile(client, cache_dir, collection, key, b)
        if img is None:
            continue
        n_img += 1
        cars += in_lot(detector.detect(img, b), lot)
    if n_img == 0:
        return dict(cars="", quality_flag="no_image", mean_conf="", detections=[])
    cars = dedupe(cars)
    conf = [c["confidence"] for c in cars]
    return dict(cars=len(cars), quality_flag="ok", mean_conf=round(sum(conf) / len(conf), 3) if conf else "",
                detections=cars)


# ---------------------------------------------------------------- batch
def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _append(path: Path, rows: list[dict]):
    with _write_lock:
        new = not path.exists()
        with open(path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_COLS)
            if new:
                w.writeheader()
            w.writerows(rows)


def run(real_dir: Path, cache_dir: Path, client, detector, buildings: list[str] | None = None, limit: int = 0,
        workers: int = 3, tile_m: float = 60.0, all_pairs: bool = False, out_name: str = "car_counts_yolo.csv",
        log=print) -> int:
    vb = {r["building_id"]: r for r in _read(real_dir / "vexcel_buildings.csv")}  # last row per building wins
    sam = _read(real_dir / "car_counts.csv")
    if not sam:
        raise SystemExit("data/real/car_counts.csv not found: run the sam3 batch first (it defines the lots and captures)")
    skip_flags = set() if all_pairs else {"not_measurable"}
    pairs: dict[str, list[str]] = {}
    for r in sam:
        if r["quality_flag"] in skip_flags or r["building_id"] not in vb:
            continue
        if buildings and r["building_id"] not in buildings:
            continue
        pairs.setdefault(r["building_id"], [])
        if r["capture_id"] not in pairs[r["building_id"]]:
            pairs[r["building_id"]].append(r["capture_id"])
    out = real_dir / out_name
    version = detector.model_version
    # a pair counts as done only if it was counted with these exact settings and didn't error;
    # change the model, confidence or resolution and the batch recounts from the cached tiles (no API calls)
    done = {(r["building_id"], r["capture_id"]) for r in _read(out)
            if r.get("model_version") == version and r["quality_flag"] != "error"}
    bids = [b for b in pairs if any((b, c) not in done for c in pairs[b])]
    if limit:
        bids = bids[:limit]
    log(f"{len(bids)} buildings to count with YOLO ({len(done)} building-captures already done with {version}), "
        f"{workers} workers")

    def one(bid: str) -> tuple[str, int, int]:
        lot = swkt.loads(vb[bid]["lot_wkt"])
        rows = []
        for cap in pairs[bid]:
            if (bid, cap) in done:
                continue
            try:
                r = count_pair(client, detector, cache_dir, lot, cap, tile_m)
            except Exception as e:  # rate limit after retries, network: record and move on
                r = dict(cars="", quality_flag="error", mean_conf="")
                log(f"   {bid} {cap}: {str(e)[:120]}")
            rows.append(dict(building_id=bid, capture_id=cap, cars=r["cars"], quality_flag=r["quality_flag"],
                             mean_conf=r["mean_conf"], detector="yolo", model_version=version))
        _append(out, rows)
        return bid, len(rows), sum(1 for x in rows if x["quality_flag"] == "ok")

    t0 = time.time()
    with ThreadPoolExecutor(max(1, workers)) as ex:
        futs = [ex.submit(one, b) for b in bids]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                bid, n, ok = f.result()
                log(f"[{i}/{len(bids)}] {bid}: {ok}/{n} captures counted  ({time.time() - t0:.0f}s)")
            except Exception as e:
                log(f"[{i}/{len(bids)}] FAILED {str(e)[:160]}")
    return len(bids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--building", action="append", help="only these building ids (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="max buildings this run (0 = all)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--tile-m", type=float, default=60.0)
    ap.add_argument("--all-pairs", action="store_true", help="also count pairs sam3 skipped as garages")
    a = ap.parse_args()
    from parallax.config import DATA_DIR
    from parallax.vexcel import VexcelClient
    from parallax.yolo import YoloDetector
    run(DATA_DIR / "real", DATA_DIR / "imagery_tiles", VexcelClient(), YoloDetector(), buildings=a.building,
        limit=a.limit, workers=a.workers, tile_m=a.tile_m, all_pairs=a.all_pairs)
    print(f"\nDone. Compare with: python -m scripts.compare_detectors")


if __name__ == "__main__":
    sys.exit(main())
