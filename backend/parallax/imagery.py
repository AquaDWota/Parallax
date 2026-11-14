"""Real Vexcel imagery for a building's lot, per capture (collection), cached on disk.

    data/imagery/<building_id>/<capture_id>.jpg        lot outlined in stall-paint yellow
    data/imagery/<building_id>/<capture_id>_boxes.jpg  same, plus a box on every detected car

The API serves the cached file (boxes version first). On a cache miss in real mode it fetches the plain
version from Vexcel on the spot - the key stays on the server. scripts/fetch_images.py prefetches
everything (and the boxes versions) so a demo never waits on the network.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import config

log = logging.getLogger("parallax.imagery")
IMG_DIR = config.DATA_DIR / "imagery"
LOT_COLOR = "rgb(242,194,48)"
CAR_COLOR = "rgb(0,229,255)"
TILE_M = float(__import__("os").environ.get("PARALLAX_TILE_M", "60"))


def cache_path(building_id: str, capture_id: str, boxes: bool = False) -> Path:
    return IMG_DIR / building_id / f"{capture_id}{'_boxes' if boxes else ''}.jpg"


def cached(building_id: str, capture_id: str) -> Path | None:
    for boxes in (True, False):
        p = cache_path(building_id, capture_id, boxes)
        if p.exists() and p.stat().st_size > 1000:
            return p
    return None


@lru_cache(maxsize=1)
def _lots() -> dict:
    f = config.DATA_DIR / "real" / "vexcel_buildings.csv"
    if not f.exists():
        return {}
    df = pd.read_csv(f, usecols=["building_id", "lot_wkt"]).dropna().drop_duplicates("building_id", keep="last")
    return dict(zip(df.building_id, df.lot_wkt))


@lru_cache(maxsize=1)
def _client():
    from .vexcel import VexcelClient
    return VexcelClient()


def can_fetch() -> bool:
    return config.DATA_MODE == "real" and bool(config.VEXCEL_API_KEY)


def fetch(building_id: str, capture_id: str, boxes: bool = False, size: str = "640,640") -> Path | None:
    """Fetch one lot image from Vexcel and cache it. Returns the path, or None on failure."""
    lot = _lots().get(building_id)
    if not lot:
        return None
    out = cache_path(building_id, capture_id, boxes)
    out.parent.mkdir(parents=True, exist_ok=True)
    from .vexcel import drawing_for
    c = _client()
    drawing = drawing_for(lot, LOT_COLOR, 3)
    try:
        if boxes:
            det = c.detect_cars_tiled(lot, collection=capture_id, tile_m=TILE_M)
            drawing += [{"wkt": d["bbox"], "outline-color": CAR_COLOR, "outline-width": 2}
                        for d in det["detections"] if d.get("bbox")]
        img = c.ortho(lot, collection=capture_id, buffer_m=15, drawing=drawing, dims=size)
    except Exception as e:  # missing collection here, rate limit after retries, network
        log.warning("image fetch failed for %s %s: %s", building_id, capture_id, str(e)[:200])
        return None
    if not img or len(img) < 1000:
        return None
    out.write_bytes(img)
    return out
