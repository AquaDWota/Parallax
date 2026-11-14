"""Compare YOLO and sam3 car counts, and draw both detectors' boxes for a hand-count check.

    python -m scripts.compare_detectors                          # report from the two count files
    python -m scripts.compare_detectors --images P239920 P240089 # + box images (needs the Vexcel key)
    python -m scripts.compare_detectors --images P239920 --capture us-tx-houston-2022

Report (F8): pairs counted by both detectors; Pearson and Spearman correlation; median YOLO/sam3 ratio;
per-building correlation; the 20 biggest disagreements. Saved to vexcel_output/compare/.
Images (F9): the lot at native resolution with the lot outline (yellow), sam3 boxes (cyan) and YOLO boxes
(magenta), plus both counts, in vexcel_output/compare/<building>_<capture>.jpg. If the magenta boxes sit on
the cars, the pixel-to-lon/lat mapping is right (acceptance check 2).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LOT, SAM3, YOLO = (242, 194, 48), (0, 229, 255), (255, 0, 200)


def report(real_dir: Path, out_dir: Path, yolo_file: str = "car_counts_yolo.csv", log=print) -> dict:
    sam = pd.read_csv(real_dir / "car_counts.csv").drop_duplicates(["building_id", "capture_id"], keep="last")
    yol = pd.read_csv(real_dir / yolo_file).drop_duplicates(["building_id", "capture_id"], keep="last")
    m = sam.merge(yol, on=["building_id", "capture_id"], suffixes=("_sam3", "_yolo"))
    m = m[(m.quality_flag_sam3 == "ok") & (m.quality_flag_yolo == "ok")].copy()
    m["cars_sam3"] = pd.to_numeric(m.cars_sam3, errors="coerce")
    m["cars_yolo"] = pd.to_numeric(m.cars_yolo, errors="coerce")
    m = m.dropna(subset=["cars_sam3", "cars_yolo"])
    if len(m) < 3:
        log(f"only {len(m)} building-captures counted by both detectors - run more of the YOLO batch first")
        return {"n_pairs": int(len(m))}
    both = m[(m.cars_sam3 > 0) & (m.cars_yolo > 0)]
    ratio = (both.cars_yolo / both.cars_sam3)
    per_b = []
    for b, g in m.groupby("building_id"):
        r = g.cars_sam3.corr(g.cars_yolo) if len(g) >= 4 and g.cars_sam3.std() > 0 and g.cars_yolo.std() > 0 else np.nan
        per_b.append(dict(building_id=b, n=len(g), r=round(r, 2) if r == r else None,
                          median_ratio=round(float((g.cars_yolo / g.cars_sam3.replace(0, np.nan)).median()), 2)
                          if (g.cars_sam3 > 0).any() else None,
                          sam3_mean=round(g.cars_sam3.mean(), 1), yolo_mean=round(g.cars_yolo.mean(), 1)))
    per_b = pd.DataFrame(per_b)
    m["abs_diff"] = (m.cars_yolo - m.cars_sam3).abs()
    m["log_ratio"] = np.log((m.cars_yolo + 1) / (m.cars_sam3 + 1))
    worst = m.reindex(m.log_ratio.abs().sort_values(ascending=False).index).head(20)
    summary = dict(
        n_pairs=int(len(m)), n_buildings=int(m.building_id.nunique()),
        pearson_r=round(float(m.cars_sam3.corr(m.cars_yolo)), 3),
        spearman_r=round(float(m.cars_sam3.corr(m.cars_yolo, method="spearman")), 3),
        median_ratio_yolo_over_sam3=round(float(ratio.median()), 2) if len(ratio) else None,
        total_sam3=int(m.cars_sam3.sum()), total_yolo=int(m.cars_yolo.sum()),
        buildings_r_ge_0_8=int((per_b.r >= 0.8).sum()), buildings_with_r=int(per_b.r.notna().sum()),
        target_r_0_8_met=bool(m.cars_sam3.corr(m.cars_yolo) >= 0.8),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    per_b.to_csv(out_dir / "per_building.csv", index=False)
    worst[["building_id", "capture_id", "cars_sam3", "cars_yolo", "abs_diff"]].to_csv(out_dir / "disagreements.csv", index=False)
    log(f"\n{summary['n_pairs']} building-captures counted by both ({summary['n_buildings']} buildings)")
    log(f"  correlation: Pearson r = {summary['pearson_r']}, Spearman = {summary['spearman_r']}"
        f"  (target r >= 0.8: {'met' if summary['target_r_0_8_met'] else 'NOT met'})")
    log(f"  median YOLO / sam3 count ratio = {summary['median_ratio_yolo_over_sam3']}"
        f"  (totals: sam3 {summary['total_sam3']:,}, YOLO {summary['total_yolo']:,})")
    log(f"  buildings with r >= 0.8: {summary['buildings_r_ge_0_8']} of {summary['buildings_with_r']} with 4+ captures")
    log("\n20 biggest disagreements:")
    log(worst[["building_id", "capture_id", "cars_sam3", "cars_yolo"]].to_string(index=False))
    log(f"\nSaved to {out_dir}/ (summary.json, per_building.csv, disagreements.csv)")
    return summary


def draw(building: str, capture: str | None, real_dir: Path, cache_dir: Path, out_dir: Path, client, detector,
         tile_m: float = 60.0, sam3_tile_m: float = 70.0, log=print) -> Path | None:
    """Lot image with sam3 and YOLO boxes. Returns the saved path."""
    import io

    from PIL import Image, ImageDraw
    from shapely import wkt as swkt

    from parallax.yolo import lonlat_to_pixel
    from scripts.batch_yolo_counts import count_pair

    vb = pd.read_csv(real_dir / "vexcel_buildings.csv").drop_duplicates("building_id", keep="last").set_index("building_id")
    if building not in vb.index:
        log(f"{building}: not in vexcel_buildings.csv")
        return None
    lot = swkt.loads(vb.loc[building, "lot_wkt"])
    if capture is None:  # busiest sam3 capture
        sam = pd.read_csv(real_dir / "car_counts.csv")
        sam = sam[(sam.building_id == building) & (sam.quality_flag == "ok")].copy()
        sam["cars"] = pd.to_numeric(sam.cars, errors="coerce")
        if sam.empty:
            log(f"{building}: no counted capture")
            return None
        capture = sam.sort_values("cars").iloc[-1].capture_id
    from shapely.geometry import box
    bounds = lot.bounds
    img, (w, h) = client.ortho_with_size(box(*bounds).wkt, collection=capture)
    im = Image.open(io.BytesIO(img)).convert("RGB")
    d = ImageDraw.Draw(im)
    px = lambda lon, lat: lonlat_to_pixel(lon, lat, w, h, bounds)
    for poly in getattr(lot, "geoms", [lot]):
        for ring in [poly.exterior, *poly.interiors]:
            d.line([px(x, y) for x, y in ring.coords], fill=LOT, width=3)
    sam3 = client.detect_cars_tiled(lot.wkt, capture, tile_m=sam3_tile_m)
    for det in sam3["detections"]:
        if isinstance(det.get("bbox"), str):
            g = swkt.loads(det["bbox"])
            d.line([px(x, y) for x, y in g.exterior.coords], fill=SAM3, width=2)
    yolo = count_pair(client, detector, cache_dir, lot, capture, tile_m)
    for c in yolo["detections"]:
        g = swkt.loads(c["polygon"])
        d.line([px(x, y) for x, y in g.exterior.coords], fill=YOLO, width=2)
    label = f"{building} {capture}   sam3 (cyan): {sam3['count']}   YOLO (magenta): {yolo['cars']}"
    d.rectangle([0, 0, 12 + 7 * len(label), 26], fill=(0, 0, 0))
    d.text((6, 6), label, fill=(255, 255, 255))
    if max(im.size) > 2000:
        im.thumbnail((2000, 2000))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{building}_{capture}.jpg"
    im.save(path, quality=88)
    log(f"{building} {capture}: sam3 {sam3['count']}, YOLO {yolo['cars']} -> {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", default=[], help="building ids to draw")
    ap.add_argument("--capture", help="capture (collection) to draw; default = busiest sam3 capture")
    ap.add_argument("--yolo-file", default="car_counts_yolo.csv")
    a = ap.parse_args()
    from parallax.config import DATA_DIR, REPO_ROOT
    real, out = DATA_DIR / "real", REPO_ROOT / "vexcel_output" / "compare"
    if (real / a.yolo_file).exists():
        report(real, out, a.yolo_file)
    else:
        print(f"{a.yolo_file} not found yet - run python -m scripts.batch_yolo_counts first")
    if a.images:
        from parallax.vexcel import VexcelClient
        from parallax.yolo import YoloDetector
        c, det = VexcelClient(), YoloDetector()
        for b in a.images:
            try:
                draw(b, a.capture, real, DATA_DIR / "imagery_tiles", out, c, det)
            except Exception as e:
                print(f"{b}: failed {str(e)[:160]}")


if __name__ == "__main__":
    sys.exit(main())
