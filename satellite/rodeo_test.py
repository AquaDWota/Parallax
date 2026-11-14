"""Positive control: can Sentinel-2 see Houston's biggest parking lots fill during the Rodeo?

NRG Park holds tens of thousands of cars and RodeoHouston fills it daily for ~3 weeks every
Feb-Mar. If 10 m imagery can't see that, it can't see a 150-stall office lot. We measure six lot
areas plus the NRG Center roof (a fixed reference that cancels haze and sun) on every clear Jan-Apr
scene 2018-2026 and compare Rodeo days with non-Rodeo days in the same season.

Result: lots D and E light up during the Rodeo - but those are where the carnival, tents and barns
go up (lot C even lights up *before* opening, during set-up). The pure parking lots A, B, F barely
move once haze is cancelled. The satellite sees structures, not cars. See README.md.

Run:  python rodeo_test.py            (no keys; ~10 min)
      python rodeo_test.py --cached   (re-print from results/rodeo_scenes.csv)
"""
import csv
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.windows import from_bounds

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
CENTRAL = dt.timezone(dt.timedelta(hours=-6))
NRG = (-95.4107, 29.6847)

# Lot boxes in UTM 15N (EPSG:32615), picked by eye on a 2022 NAIP image of NRG Park.
X0, Y0, X1, Y1 = 265602.86, 3285161.32, 267850.46, 3287398.00
SX, SY = (X1 - X0) / 1100, (Y1 - Y0) / 1100
LOTS = {"A": (110, 410, 190, 490), "B": (340, 530, 430, 670), "C": (510, 710, 690, 870),
        "D": (770, 490, 870, 590), "E": (480, 310, 630, 390), "F": (750, 930, 870, 1080)}
ROOF = (660, 350, 870, 430)  # NRG Center roof - doesn't change with crowds
# D and E are the Rodeo carnival / livestock grounds; A, B, F are plain parking.


def utm(b):
    px0, py0, px1, py1 = b
    return (X0 + px0 * SX, Y1 - py1 * SY, X0 + px1 * SX, Y1 - py0 * SY)


# Approximate RodeoHouston dates incl. the BBQ contest the week before (2021 was cancelled).
RODEO = {2018: ("02-22", "03-18"), 2019: ("02-21", "03-17"), 2020: ("02-27", "03-11"),
         2022: ("02-24", "03-20"), 2023: ("02-23", "03-19"), 2024: ("02-22", "03-17"),
         2025: ("02-27", "03-23"), 2026: ("02-26", "03-22")}


def in_rodeo(d):
    r = RODEO.get(d.year)
    return bool(r) and dt.date.fromisoformat(f"{d.year}-{r[0]}") <= d <= dt.date.fromisoformat(f"{d.year}-{r[1]}")


def read(src, b):
    w = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
    return src.read(1, window=w).astype(float)


def measure():
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    items = []
    for y in range(2018, 2027):
        items += list(cat.search(collections=["sentinel-2-l2a"], intersects={"type": "Point", "coordinates": list(NRG)},
                                 datetime=f"{y}-01-01/{y}-04-30", query={"eo:cloud_cover": {"lt": 40}}).items())
    tiles = {}
    for it in items:
        tiles[it.properties["s2:mgrs_tile"]] = tiles.get(it.properties["s2:mgrs_tile"], 0) + 1
    tile = max(tiles, key=tiles.get)
    items = sorted([i for i in items if i.properties["s2:mgrs_tile"] == tile], key=lambda i: i.datetime)
    print(f"{len(items)} scenes, tile {tile}", file=sys.stderr)

    rows = []
    for it in items:
        try:
            off = 1000 if float(it.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
            srcs = {n: rasterio.open(it.assets[n].href) for n in ("B02", "B03", "B04", "SCL")}
            d = it.datetime.astimezone(CENTRAL).date()
            row = dict(date=d.isoformat(), weekday=d.weekday(), rodeo=int(in_rodeo(d)))
            ok = True
            for name, b in list(LOTS.items()) + [("ROOF", ROOF)]:
                bb = utm(b)
                if not np.isin(read(srcs["SCL"], bb), [4, 5, 6, 7]).mean() > 0.9:
                    ok = False
                    break
                vis = np.mean([(read(srcs[n], bb) - off) / 1e4 for n in ("B02", "B03", "B04")], axis=0)
                row[f"{name}_vis"] = round(float(vis.mean()), 5)
                row[f"{name}_std"] = round(float(vis.std()), 5)
            for s in srcs.values():
                s.close()
            if ok:
                rows.append(row)
        except Exception as e:  # noqa: BLE001
            print("skip", it.id, e, file=sys.stderr)
    with open(OUT / "rodeo_scenes.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    return rows


def summarise(rows):
    d = np.array([dt.date.fromisoformat(r["date"]) for r in rows])
    rodeo = np.array([int(r["rodeo"]) for r in rows]).astype(bool)
    doy = np.array([x.timetuple().tm_yday for x in d])
    normal = (doy >= 30) & (doy <= 110) & ~rodeo  # same season, no Rodeo
    roof = np.array([float(r["ROOF_vis"]) for r in rows])
    print(f"{len(rows)} clear scenes: {rodeo.sum()} during the Rodeo, {normal.sum()} normal days in the same season\n")

    def t(a, b):
        return (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))

    print("lot  role       brightness/roof: Rodeo vs normal (t)   texture: Rodeo vs normal (t)")
    for L in LOTS:
        v = np.array([float(r[f"{L}_vis"]) for r in rows]) / roof
        s = np.array([float(r[f"{L}_std"]) for r in rows])
        role = "carnival" if L in "DE" else "parking"
        print(f"  {L}  {role:9s}  {v[rodeo].mean():.3f} vs {v[normal].mean():.3f} (t={t(v[rodeo], v[normal]):+.1f})"
              f"          {s[rodeo].mean():.4f} vs {s[normal].mean():.4f} (t={t(s[rodeo], s[normal]):+.1f})")


if __name__ == "__main__":
    cached = OUT / "rodeo_scenes.csv"
    rows = list(csv.DictReader(open(cached))) if "--cached" in sys.argv and cached.exists() else measure()
    summarise(rows)
