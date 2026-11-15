"""Esri World Imagery Wayback: which distinct historical images exist over one building's lot.

    cd backend
    python -m scripts.wayback_probe --building P239891          # a study building (uses its lot)
    python -m scripts.wayback_probe --lat 29.7274 --lon -95.5616  # any point

For every Wayback release it fetches the lot's tiles at zoom 19 (~0.27 m/px in Houston), keeps only releases
whose pixels differ from the previous one, looks up the real capture date / resolution / source in that release's
metadata service, and saves a mosaic per distinct image to data/wayback/<id>/. Tiles are cached, so a re-run
makes no new requests. Nothing here is committed (data/ is git-ignored).

Terms: Esri World Imagery is licensed for non-commercial use; credit "Esri, Maxar, Earthstar Geographics, and the
GIS User Community" (and the provider in the metadata) wherever these images or counts appear.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

CONFIG_URL = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "wayback"
HEADERS = {"User-Agent": "parallax-hackathon-research (non-commercial)"}
S = requests.Session()
S.headers.update(HEADERS)


def get(url, **kw):
    for attempt in range(4):
        r = S.get(url, timeout=60, **kw)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        return r
    return r


def releases() -> list[dict]:
    """All releases, newest first: {num, date, url (tile template), meta (metadata MapServer)}."""
    cfg = get(CONFIG_URL).json()
    out = []
    for num, it in cfg.items():
        title = it.get("itemTitle", "")
        date = title.split("Wayback")[-1].strip(" )") if "Wayback" in title else ""
        out.append(dict(num=int(num), date=date, url=it["itemURL"], meta=it.get("metadataLayerUrl", "")))
    return sorted(out, key=lambda r: r["date"], reverse=True)


def tile_xy(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def tiles_for(bounds, z):
    (x0, y1), (x1, y0) = tile_xy(bounds[1], bounds[0], z), tile_xy(bounds[3], bounds[2], z)
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def fetch(rel, z, x, y, cache: Path) -> bytes | None:
    f = cache / str(rel["num"]) / f"{z}_{x}_{y}.jpg"
    if f.exists():
        return f.read_bytes() or None
    url = rel["url"].replace("{level}", str(z)).replace("{row}", str(y)).replace("{col}", str(x))
    r = get(url)
    f.parent.mkdir(parents=True, exist_ok=True)
    data = r.content if r.ok and r.headers.get("content-type", "").startswith("image") else b""
    f.write_bytes(data)
    return data or None


def metadata(rel, lat, lon) -> dict:
    """Capture date, resolution, source and provider at the point, from the release's metadata service."""
    if not rel["meta"]:
        return {}
    try:
        layers = get(rel["meta"], params={"f": "json"}).json().get("layers", [])
    except ValueError:
        return {}
    for lyr in layers:  # layers are per zoom range; take the first that has a polygon at the point
        r = get(f"{rel['meta']}/{lyr['id']}/query", params={
            "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false", "f": "json"})
        try:
            feats = r.json().get("features", [])
        except ValueError:
            continue
        if feats:
            a = {k.upper(): v for k, v in feats[0]["attributes"].items()}
            d = a.get("SRC_DATE2") or a.get("SRC_DATE")
            if isinstance(d, (int, float)) and d > 10_000_000_000:  # epoch ms
                d = datetime.fromtimestamp(d / 1000, tz=timezone.utc).date().isoformat()
            return dict(capture_date=str(d or ""), resolution_m=a.get("SRC_RES", ""),
                        source=a.get("SRC_DESC", ""), provider=a.get("NICE_DESC") or a.get("NICE_NAME", ""))
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--building")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--zoom", type=int, default=19)
    ap.add_argument("--max-releases", type=int, default=0, help="0 = all")
    a = ap.parse_args()

    if a.building:
        from shapely import wkt
        rows = {r["building_id"]: r for r in csv.DictReader(open(ROOT / "data/real/vexcel_buildings.csv"))}
        lot = wkt.loads(rows[a.building]["lot_wkt"])
        bounds, (lon, lat), key = lot.bounds, (lot.centroid.x, lot.centroid.y), a.building
    else:
        d = 60 / 111_320
        lat, lon, key = a.lat, a.lon, f"pt_{a.lat:.5f}_{a.lon:.5f}"
        bounds = (lon - d, lat - d, lon + d, lat + d)
    out = OUT / key
    cache = ROOT / "data" / "wayback_tiles"
    tiles = tiles_for(bounds, a.zoom)
    rels = releases()[: a.max_releases or None]
    print(f"{len(rels)} Wayback releases; {len(tiles)} tiles at zoom {a.zoom} over {key}")

    distinct, last_hash = [], None
    for rel in reversed(rels):  # oldest first, so each distinct image is listed at its first release
        imgs = [fetch(rel, a.zoom, x, y, cache) for x, y in tiles]
        if not all(imgs):
            continue
        h = hashlib.md5(b"".join(imgs)).hexdigest()
        if h == last_hash:
            continue
        last_hash = h
        m = metadata(rel, lat, lon)
        xs, ys = sorted({x for x, _ in tiles}), sorted({y for _, y in tiles})
        mosaic = Image.new("RGB", (256 * len(xs), 256 * len(ys)))
        for (x, y), b in zip(tiles, imgs):
            mosaic.paste(Image.open(io.BytesIO(b)).convert("RGB"), (256 * xs.index(x), 256 * ys.index(y)))
        out.mkdir(parents=True, exist_ok=True)
        name = f"{m.get('capture_date') or rel['date']}_r{rel['num']}.jpg"
        mosaic.save(out / name, quality=92)
        distinct.append(dict(release=rel["num"], release_date=rel["date"], image=name, **m))
        print(f"  new image in release {rel['date']}: captured {m.get('capture_date', '?')}, "
              f"{m.get('resolution_m', '?')} m, {m.get('source', '')} {m.get('provider', '')}")
    with open(out / "images.json", "w") as fh:
        json.dump(distinct, fh, indent=1)
    print(f"\n{len(distinct)} distinct images -> {out}")


if __name__ == "__main__":
    main()
