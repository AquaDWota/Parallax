"""Can free 10 m Sentinel-2 imagery see an office parking lot fill and empty?

Test lot: 2646 Loop, Houston (CoStar 239748) - a ~3-storey office on a concrete lot.
For every clear Sentinel-2 L2A scene 2018-2026 we measure the lot ring (120 m square around the
building minus the central 50 m) and ask two questions where the answer is known:
  1. weekday (full) vs weekend (empty)  - the biggest swing a lot ever makes
  2. pre-COVID weekdays vs Apr 2020 - Jun 2021 weekdays (offices emptied)
If the satellite can see cars, both should show up. Result: neither does (see README.md).

Run:  pip install -r requirements.txt && python office_lot_test.py   (no keys; Microsoft Planetary Computer)
Writes results/office_lot_scenes.csv and prints the summary.
"""
import csv
import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

LAT, LON = 29.6794344, -95.4207655
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
CENTRAL = dt.timezone(dt.timedelta(hours=-6))


def box(half_m):
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(LAT)))
    return (LON - dlon, LAT - dlat, LON + dlon, LAT + dlat)


OUTER, INNER = box(60), box(25)


def read(href, bounds):
    with rasterio.open(href) as src:
        b = transform_bounds("EPSG:4326", src.crs, *bounds)
        w = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
        return src.read(1, window=w).astype(float)


def measure():
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["sentinel-2-l2a"],
                            intersects={"type": "Point", "coordinates": [LON, LAT]},
                            datetime="2018-01-01/2026-11-01", query={"eo:cloud_cover": {"lt": 30}}).items())
    tiles = {}
    for it in items:
        tiles[it.properties["s2:mgrs_tile"]] = tiles.get(it.properties["s2:mgrs_tile"], 0) + 1
    tile = max(tiles, key=tiles.get)  # one tile only, so every scene has the same pixel grid
    items = sorted([i for i in items if i.properties["s2:mgrs_tile"] == tile], key=lambda i: i.datetime)
    print(f"{len(items)} scenes on tile {tile}", file=sys.stderr)

    rows = []
    for k, it in enumerate(items):
        try:
            # processing baseline 04.00+ (from Jan 2022) adds a +1000 offset to reflectance
            off = 1000 if float(it.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
            bands = {n: (read(it.assets[n].href, OUTER) - off) / 1e4 for n in ("B02", "B03", "B04", "B08")}
            scl = read(it.assets["SCL"].href, OUTER)
            h, w = bands["B04"].shape
            yy, xx = np.mgrid[0:h, 0:w]
            fy = (INNER[1] - OUTER[1]) / (OUTER[3] - OUTER[1])
            fx = (INNER[0] - OUTER[0]) / (OUTER[2] - OUTER[0])
            ring = ~((xx >= fx * w) & (xx < (1 - fx) * w) & (yy >= fy * h) & (yy < (1 - fy) * h))
            scl_up = np.kron(scl, np.ones((2, 2)))[:h, :w]  # SCL is 20 m
            m = ring & np.isin(scl_up, [4, 5, 6, 7])        # vegetation / bare / water / unclassified: no cloud
            if m.sum() < 0.8 * ring.sum():
                continue
            vis = (bands["B02"] + bands["B03"] + bands["B04"]) / 3
            d = it.datetime.astimezone(CENTRAL).date()
            rows.append(dict(date=d.isoformat(), weekday=d.weekday(), vis=round(float(vis[m].mean()), 5),
                             vis_std=round(float(vis[m].std()), 5), n_px=int(m.sum())))
        except Exception as e:  # noqa: BLE001 - a bad tile shouldn't stop the run
            print("skip", it.id, e, file=sys.stderr)
        if k % 50 == 0:
            print(k, len(rows), file=sys.stderr)
    with open(OUT / "office_lot_scenes.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    return rows


def summarise(rows):
    d = np.array([dt.date.fromisoformat(r["date"]) for r in rows])
    v = np.array([float(r["vis"]) for r in rows])
    wd = np.array([int(r["weekday"]) for r in rows])
    month = np.array([x.month for x in d])
    resid = v - np.array([v[month == m].mean() for m in month])  # remove the seasonal pattern
    work = wd < 5
    gap = resid[work].mean() - resid[~work].mean()
    noise = resid.std()
    print(f"\n{len(rows)} clear scenes, {work.sum()} weekdays / {(~work).sum()} weekends")
    print(f"full (weekday) minus empty (weekend) brightness: {100 * gap / v.mean():+.1f}%")
    print(f"photo-to-photo noise after removing season:       {100 * noise / v.mean():.1f}%")
    print(f"signal / noise per photo: {abs(gap) / noise:.2f}")
    for drop in (1.0, 0.3):
        n = (2 * 1.96 * noise / (abs(gap) * drop)) ** 2
        print(f"photos per period needed to detect a {int(drop * 100)}% emptying: ~{n:.0f}")
    pre = np.array([x < dt.date(2020, 3, 15) for x in d]) & work
    cov = np.array([dt.date(2020, 4, 1) <= x < dt.date(2021, 7, 1) for x in d]) & work
    print(f"weekday brightness pre-COVID {v[pre].mean():.4f} vs Apr 2020-Jun 2021 {v[cov].mean():.4f}")


if __name__ == "__main__":
    cached = OUT / "office_lot_scenes.csv"
    rows = list(csv.DictReader(open(cached))) if "--cached" in sys.argv and cached.exists() else measure()
    summarise(rows)
