"""Find the detection tile size where car counts stop rising. RUN ON YOUR LAPTOP (~2 min).

    python -m scripts.calibrate_tiles                       # 3 big lots from data/real/vexcel_buildings.csv
    python -m scripts.calibrate_tiles --building P240089

For each lot it counts cars on the newest capture with the whole lot in one call (0) and with tiles of
150, 100, 70, 50 and 35 m. If counts rise as tiles shrink, /elements/detect is downsampling. Pick the
largest tile size whose count is within ~5% of the smallest - fewer API calls for the same count.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from parallax.config import DATA_DIR
from parallax.lots import lot_polygon_v2
from parallax.vexcel import ORTHO_NAMES, VexcelClient

SIZES = [0, 150, 100, 70, 50, 35]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--building", action="append", help="building id (repeatable)")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    vb = pd.read_csv(DATA_DIR / "real" / "vexcel_buildings.csv").drop_duplicates("building_id", keep="last")
    props = pd.read_csv(DATA_DIR / "real" / "costar_properties.csv")[["building_id", "surface_spaces"]]
    vb = vb.merge(props, on="building_id", how="left")
    if a.building:
        pick = vb[vb.building_id.isin(a.building)]
    else:  # big lots with a CoStar stall count: where downsampling would show
        pick = vb[vb.building_id.str.startswith("P") & (vb.surface_spaces >= 150)].nlargest(a.n, "lot_area_m2")
    c = VexcelClient()
    rows = []
    for b in pick.itertuples():
        prop = c.parcel(b.lat, b.lon)
        feat = prop["features"][0] if prop and prop.get("features") else None
        lot, ring_m, lot_m2 = lot_polygon_v2(feat, b.lat, b.lon, b.surface_spaces)
        cols = [x.get("collection") for x in c.list_collections(lot.wkt, "oblique")]
        cols = sorted({n for n in cols if n and ORTHO_NAMES.match(n)})
        if not cols:
            print(f"{b.building_id}: no ortho collections")
            continue
        newest = cols[-1]
        print(f"\n{b.building_id} {getattr(b, 'name', '')}: lot {lot_m2:,.0f} m2 (ring {ring_m:.0f} m), "
              f"CoStar surface stalls {b.surface_spaces}, capture {newest}")
        for t in SIZES:
            try:
                d = c.detect_cars_tiled(lot.wkt, newest, tile_m=t)
                print(f"   tile {'whole lot' if t == 0 else f'{t:>3} m':>9}: {d['count']:>4} cars  ({d['calls']} calls)")
                rows.append(dict(building=b.building_id, tile_m=t, cars=d["count"], calls=d["calls"]))
            except Exception as e:
                print(f"   tile {t}: failed {str(e)[:120]}")
    if rows:
        df = pd.DataFrame(rows)
        best = df.groupby("building").cars.transform("max")
        df["share_of_max"] = (df.cars / best).round(2)
        print("\nshare of the highest count, by tile size:")
        print(df.groupby("tile_m").agg(share_of_max=("share_of_max", "mean"), calls=("calls", "mean")).round(2).to_string())
        print("\nPick the largest tile size with share_of_max >= 0.95, then:")
        print("  python -m scripts.batch_car_counts --buildings ../data/real/study_buildings_v3.csv --fresh "
              "--archive-tag v2 --tile-m <SIZE> --workers 4")


if __name__ == "__main__":
    sys.exit(main())
