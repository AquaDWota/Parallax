"""Vexcel API 2.0 client, following the hackathon quickstart.

Key points from the quickstart:
  * base https://api.vexcelgroup.com/v2, header X-API-KEY, key from env VEXCEL_API_KEY
  * WKT is LONGITUDE first: POINT(lon lat); always send srid=4326
  * layer "urban,urban-r,wide-area,urban-g" = best available (urban = 7.5 cm ortho + obliques)
  * /ortho/extract and /oriented/extract return image BYTES, not JSON
  * 429 -> exponential backoff (1, 2, 4, 8, 16 s)
  * /elements/detect runs sam3 open-vocabulary detection: label "car" counts cars, no training

Open question to confirm with the Vexcel engineers: how many historical collections exist for
Houston and LA (we want 2018-2026). `list_collections()` answers it for any spot.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any

import requests

from . import config

API = "https://api.vexcelgroup.com/v2"
LAYERS = "urban,urban-r,wide-area,urban-g"


class VexcelClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 5):
        key = api_key or config.VEXCEL_API_KEY
        if not key:
            raise RuntimeError("VEXCEL_API_KEY is not set (put it in .env at the repo root)")
        self.headers = {"X-API-KEY": key}
        self.max_retries = max_retries

    # ---------- transport ----------
    def send(self, method: str, path: str, **kw) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            r = requests.request(method, f"{API}/{path}", headers=self.headers, **kw)
            if r.status_code != 429 or attempt == self.max_retries:
                return r
            time.sleep(min(2 ** attempt, 30) + random.random())
        return r

    def get(self, path: str, **params) -> dict:
        r = self.send("GET", path, params=params, timeout=120)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict, expect_json: bool = True):
        r = self.send("POST", path, json=body, timeout=300)
        if not r.ok:
            raise RuntimeError(f"/{path} failed ({r.status_code}): {r.text[:500]}")
        return r.json() if expect_json else r.content

    # ---------- property elements ----------
    def parcel(self, lat: float, lon: float, include: str = "precomputed") -> dict | None:
        """Parcel polygon + attributes (building-type, structures with footprints) at a point."""
        r = self.send("GET", "property/extract", timeout=120, params={
            "wkt": point(lat, lon), "srid": 4326, "layer": LAYERS, "latest": "true",
            "include": include, "unit-system": "imperial"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def parcels_in_area(self, wkt: str, page: int = 1, page_size: int = 500, **filters) -> dict:
        """Every parcel in a polygon (paged, up to 500 per page). Use to enumerate buildings."""
        return self.get("property/extract", wkt=wkt, srid=4326, layer=LAYERS, latest="true",
                        include="building-type,footprint-wkt,structure", page=page,
                        **{"page-size": page_size}, **filters)

    # ---------- coverage / time series ----------
    def list_collections(self, wkt: str, product_type: str = "oblique") -> list[dict]:
        """Which collections (capture campaigns) cover this spot, with capture dates."""
        r = self.send("GET", "oriented/collections", timeout=120, params={
            "wkt": wkt, "srid": 4326, "product-type": product_type,
            "include": "product-type,collection,last-capture-date,first-capture-date"})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [f["properties"] for f in r.json().get("features", [])]

    def query_images(self, wkt: str, product_type: str = "nadir") -> list[dict]:
        """Every raw oriented image of a spot with capture date - the time-series source."""
        r = self.send("GET", "oriented/query", timeout=120, params={
            "wkt": wkt, "srid": 4326, "product-type": product_type,
            "include": "collection,capture-date,product-type", "order-by": "capture-date"})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [f["properties"] for f in r.json().get("features", [])]

    # ---------- imagery ----------
    def ortho(self, wkt: str, collection: str | None = None, buffer_m: float = 0,
              drawing: list | None = None, dims: str | None = "800,800") -> bytes:
        body: dict[str, Any] = {"wkt": wkt, "srid": 4326, "layer": LAYERS, "buffer-meter": buffer_m,
                                "crop": "bounding_box", "image-format": "jpeg"}
        if collection:
            body["collection"] = collection
        if drawing:
            body["drawing"] = drawing
        if dims:
            body["destination-dimensions"] = dims
        return self.post("ortho/extract", body, expect_json=False)

    # ---------- car detection ----------
    def detect_cars(self, wkt: str, collection: str | None = None, threshold: float = 0.5) -> dict:
        """Run Vexcel's sam3 detector for 'car' on the ortho of `wkt` (optionally a given collection).
        Returns {"count", "detections":[{bbox, confidence}], "raw"}."""
        req: dict[str, Any] = {"layer": LAYERS, "srid": 4326, "wkt": wkt, "crop": "bounding_box"}
        if collection:
            req["collection"] = collection
        res = self.post("elements/detect", {
            "wkt": wkt, "srid": 4326, "buffer-meter": 0,
            "images": [{"endpoint": "ortho/extract", "request": req}],
            "model-input": {"elements": [{"label": "car", "model": "sam3", "detection-threshold": threshold}],
                            "include": ["bbox", "confidence"]},
        })
        dets = [d for f in res.get("features", []) if f["properties"].get("label") == "car"
                for d in f["properties"].get("detections", [])]
        return {"count": len(dets), "detections": [{"bbox": d.get("bbox"), "confidence": d.get("confidence")} for d in dets],
                "raw": res}

    # ---------- semantic search ----------
    def search(self, wkt: str, text: str, n: int = 50) -> list[dict]:
        """Embedding search, e.g. text='surface parking lot' to find measurable lots in an area."""
        res = self.post("embedding/extract", {"wkt": wkt, "srid": 4326, "search-text": text,
                                              "include": "score,geometry,collection",
                                              "total-records": n, "page-size": min(n, 100)})
        return res.get("features", [])


def point(lat: float, lon: float) -> str:
    return f"POINT({lon} {lat})"  # lon first!


def square_around(lat: float, lon: float, half_m: float) -> str:
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def lot_polygon(parcel_feature: dict) -> str:
    """Parking area estimate = parcel minus building footprints (plan join #1)."""
    from shapely import wkt as swkt
    from shapely.geometry import shape

    g = parcel_feature["geometry"]
    parcel = swkt.loads(g) if isinstance(g, str) else shape(g)
    for s in parcel_feature["properties"].get("structures", []):
        fp = s.get("footprint-wkt") or s.get("footprint.wkt")
        if fp:
            parcel = parcel.difference(swkt.loads(fp))
    return parcel.wkt
