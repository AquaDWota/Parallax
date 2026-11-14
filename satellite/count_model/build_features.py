"""Go/no-go experiment: can a model trained on Vexcel car counts read lot fill from Sentinel-2?

For every Vexcel flight over two dense clusters (Westchase, Houston; El Segundo, LA) we take the
Sentinel-2 L2A scenes inside that flight's capture window (Vexcel only gives a date range, so we
average the clear scenes in it) and measure each lot polygon: mean reflectance in 6 bands, visible
texture, NDVI. Output: one row per (lot, Vexcel flight) with the features + Vexcel's car count.

Needs (git-ignored, licensed): data/real/vexcel_buildings.csv, car_counts.csv, captures.csv.
Writes results/features.csv (derived numbers only - no imagery).
Run: python build_features.py   (~10-20 min, no keys)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds
from shapely import wkt
from shapely.geometry import mapping

HERE = Path(__file__).resolve().parent
REAL = HERE.parents[1] / "data" / "real"
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)

AREAS = ["Westchase", "El Segundo"]
MAX_WINDOW_DAYS = 60      # skip flights whose date range is too wide to match against
PAD_DAYS = 2
BANDS_10 = ["B02", "B03", "B04", "B08"]
BANDS_20 = ["B11", "B12"]
CLEAR = [4, 5, 6, 7]      # SCL: vegetation, bare, water, unclassified


def load():
    vb = pd.read_csv(REAL / "vexcel_buildings.csv").drop_duplicates("building_id", keep="last")
    cc = pd.read_csv(REAL / "car_counts.csv").drop_duplicates(["building_id", "capture_id"], keep="last")
    cap = pd.read_csv(REAL / "captures.csv").drop_duplicates("capture_id")
    cap["first"] = pd.to_datetime(cap["first_capture"])
    cap["last"] = pd.to_datetime(cap["last_capture"])
    cap["span"] = (cap["last"] - cap["first"]).dt.days + 1
    return vb, cc, cap


def cluster(vb, area):
    v = vb[vb.area == area]
    lat0, lat1, lon0, lon1 = v.lat.min() - 0.005, v.lat.max() + 0.005, v.lon.min() - 0.005, v.lon.max() + 0.005
    lots = vb[vb.lat.between(lat0, lat1) & vb.lon.between(lon0, lon1) & vb.lot_wkt.notna()]
    lots = lots.drop_duplicates("lot_wkt").copy()   # a few discovered parcels share one lot
    lots["geom"] = lots.lot_wkt.map(wkt.loads)
    minx, miny, maxx, maxy = np.array([g.bounds for g in lots.geom]).T
    bbox = (minx.min() - 0.002, miny.min() - 0.002, maxx.max() + 0.002, maxy.max() + 0.002)
    return lots, bbox


def read_window(href, crs_bounds):
    with rasterio.open(href) as src:
        w = from_bounds(*crs_bounds, transform=src.transform).round_offsets().round_lengths()
        return src.read(1, window=w).astype(float), src.window_transform(w), src.crs


def scene_features(item, lots, bbox):
    off = 1000 if float(item.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
    with rasterio.open(item.assets["B04"].href) as src:
        crs = src.crs
    cb = transform_bounds("EPSG:4326", crs, *bbox)
    arr, tr = {}, None
    for b in BANDS_10:
        a, t, _ = read_window(item.assets[b].href, cb)
        arr[b], tr = (a - off) / 1e4, t
    shape = arr["B04"].shape
    for b in BANDS_20 + ["SCL"]:
        a, _, _ = read_window(item.assets[b].href, cb)
        a = np.kron(a, np.ones((2, 2)))[: shape[0], : shape[1]]  # 20 m -> 10 m grid
        if a.shape != shape:
            a = np.pad(a, ((0, shape[0] - a.shape[0]), (0, shape[1] - a.shape[1])), mode="edge")
        arr[b] = a if b == "SCL" else (a - off) / 1e4
    vis = (arr["B02"] + arr["B03"] + arr["B04"]) / 3
    ndvi = (arr["B08"] - arr["B04"]) / (arr["B08"] + arr["B04"] + 1e-9)
    clear = np.isin(arr["SCL"], CLEAR)
    rows = []
    for r in lots.itertuples():
        g = transform_geom("EPSG:4326", crs, mapping(r.geom))
        inside = ~geometry_mask([g], out_shape=shape, transform=tr, all_touched=False)
        n = int(inside.sum())
        if n < 20:
            continue
        m = inside & clear
        if m.sum() < 0.8 * n:
            continue
        f = {f"m_{b}": float(arr[b][m].mean()) for b in BANDS_10 + BANDS_20}
        f.update(vis_std=float(vis[m].std()), ndvi=float(ndvi[m].mean()), n_px=n, building_id=r.building_id)
        rows.append(f)
    return rows


def main():
    vb, cc, cap = load()
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    out = []
    for area in AREAS:
        lots, bbox = cluster(vb, area)
        counts = cc[cc.building_id.isin(lots.building_id) & cc.quality_flag.eq("ok")]
        flights = cap[cap.capture_id.isin(counts.capture_id) & (cap.span <= MAX_WINDOW_DAYS)]
        print(f"== {area}: {len(lots)} lots, {len(flights)} flights", file=sys.stderr, flush=True)
        for fl in flights.itertuples():
            start = (fl.first - pd.Timedelta(days=PAD_DAYS)).date()
            end = (fl.last + pd.Timedelta(days=PAD_DAYS)).date()
            items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{start}/{end}",
                                    query={"eo:cloud_cover": {"lt": 40}}).items())
            if not items:
                continue
            tiles = pd.Series([i.properties["s2:mgrs_tile"] for i in items]).value_counts()
            items = [i for i in items if i.properties["s2:mgrs_tile"] == tiles.index[0]]
            per_scene = []
            for it in items:
                try:
                    for r in scene_features(it, lots, bbox):
                        r["scene_date"] = it.datetime.date().isoformat()
                        r["weekday"] = it.datetime.weekday() < 5
                        per_scene.append(r)
                except Exception as e:  # noqa: BLE001
                    print("  skip", it.id, e, file=sys.stderr)
            if not per_scene:
                continue
            ps = pd.DataFrame(per_scene)
            feat_cols = [c for c in ps.columns if c.startswith("m_")] + ["vis_std", "ndvi"]
            agg = ps.groupby("building_id").agg(**{c: (c, "mean") for c in feat_cols},
                                                n_scenes=("scene_date", "nunique"),
                                                n_weekday=("weekday", "sum"),
                                                n_px=("n_px", "first")).reset_index()
            agg["capture_id"], agg["area"] = fl.capture_id, area
            out.append(agg)
            print(f"  {fl.capture_id}: {len(items)} scenes, {agg.n_scenes.max()} clear, {len(agg)} lots", file=sys.stderr, flush=True)
    feats = pd.concat(out, ignore_index=True)
    feats = feats.merge(counts_all(cc), on=["building_id", "capture_id"], how="inner")
    feats = feats.merge(vb[["building_id", "stall_capacity_est", "lot_area_m2"]], on="building_id", how="left")
    feats.to_csv(OUT / "features.csv", index=False)
    print(f"wrote {len(feats)} rows -> {OUT / 'features.csv'}", file=sys.stderr)


def counts_all(cc):
    c = cc[cc.quality_flag.eq("ok")][["building_id", "capture_id", "cars"]]
    return c.astype({"cars": float})


if __name__ == "__main__":
    main()
