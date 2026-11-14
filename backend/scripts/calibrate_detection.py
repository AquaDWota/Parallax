"""Compare car-detector settings on a few real lots and save a boxed image for each. RUN ON YOUR LAPTOP (~5 min).

    python -m scripts.calibrate_detection
    python -m scripts.calibrate_detection --building P240089 --building P240117

For each lot (its busiest capture so far) it tries the confidence thresholds and labels below, at 70 m tiles,
prints the counts, and writes vexcel_output/calib/<building>_<setting>.jpg with every detection boxed.
Look at the images: pick the setting that boxes most of the parked cars without boxing roofs, AC units or
shadows. Then put it in .env, e.g.
    PARALLAX_DETECT_THRESHOLD=0.25
    PARALLAX_DETECT_LABELS=car,truck,van
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

import pandas as pd

from parallax.config import DATA_DIR, REPO_ROOT
from parallax.vexcel import VexcelClient, drawing_for

SETTINGS = [
    ("t50_car", 0.50, ("car",)),
    ("t35_car", 0.35, ("car",)),
    ("t25_car", 0.25, ("car",)),
    ("t15_car", 0.15, ("car",)),
    ("t35_vehicles", 0.35, ("car", "truck", "van")),
    ("t25_vehicles", 0.25, ("car", "truck", "van", "suv")),
]
COLORS = {"car": "rgb(0,229,255)", "truck": "rgb(255,64,129)", "van": "rgb(118,255,3)", "suv": "rgb(255,145,0)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--building", action="append")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--tile-m", type=float, default=70)
    a = ap.parse_args()
    R = DATA_DIR / "real"
    vb = pd.read_csv(R / "vexcel_buildings.csv").drop_duplicates("building_id", keep="last")
    cc = pd.read_csv(R / "car_counts.csv")
    props = pd.read_csv(R / "costar_properties.csv")[["building_id", "surface_spaces", "address"]]
    vb = vb.merge(props, on="building_id", how="left")
    ok = cc[cc.quality_flag == "ok"].dropna(subset=["cars"])
    busiest = ok.sort_values("cars").groupby("building_id").tail(1).set_index("building_id")
    if a.building:
        pick = vb[vb.building_id.isin(a.building)]
    else:  # typical office-park lots: 100+ CoStar stalls, middle-sized outline
        cand = vb[vb.building_id.isin(busiest.index) & (vb.surface_spaces >= 100)]
        cand = cand[cand.lot_area_m2.between(cand.lot_area_m2.quantile(0.3), cand.lot_area_m2.quantile(0.7))]
        pick = cand.sample(min(a.n, len(cand)), random_state=1)
    out = REPO_ROOT / "vexcel_output" / "calib"
    out.mkdir(parents=True, exist_ok=True)
    c = VexcelClient()
    rows = []
    for b in pick.itertuples():
        if b.building_id not in busiest.index:
            print(f"{b.building_id}: no counted capture yet")
            continue
        cap = busiest.loc[b.building_id, "capture_id"]
        print(f"\n{b.building_id} {b.address}: CoStar surface stalls {b.surface_spaces}, capture {cap}, "
              f"current count {int(busiest.loc[b.building_id, 'cars'])}")
        for name, thr, labels in SETTINGS:
            try:
                d = c.detect_cars_tiled(b.lot_wkt, cap, tile_m=a.tile_m, threshold=thr, labels=labels)
            except Exception as e:
                print(f"   {name:13s} failed: {str(e)[:120]}")
                continue
            by = Counter(x.get("label") for x in d["detections"])
            conf = sorted(x.get("confidence") or 0 for x in d["detections"])
            low = sum(1 for x in conf if x < 0.35)
            print(f"   {name:13s} {d['count']:>4} detections  {dict(by)}  (below 0.35 confidence: {low})")
            rows.append(dict(building=b.building_id, setting=name, count=d["count"]))
            drawing = drawing_for(b.lot_wkt, "rgb(242,194,48)", 3) + [
                {"wkt": x["bbox"], "outline-color": COLORS.get(x.get("label"), "rgb(0,229,255)"), "outline-width": 2}
                for x in d["detections"] if isinstance(x.get("bbox"), str)]
            try:
                img = c.ortho(b.lot_wkt, collection=cap, buffer_m=10, drawing=drawing, dims="1000,1000")
                (out / f"{b.building_id}_{name}.jpg").write_bytes(img)
            except Exception as e:
                print(f"      (image failed: {str(e)[:80]})")
    if rows:
        df = pd.DataFrame(rows).pivot(index="building", columns="setting", values="count")
        print("\n" + df[[s[0] for s in SETTINGS if s[0] in df.columns]].to_string())
        print(f"\nImages: {out}  - open them and compare, then tell Claude which setting looks right.")


if __name__ == "__main__":
    sys.exit(main())
