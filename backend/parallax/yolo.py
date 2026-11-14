"""Open-source car detector: a pretrained Ultralytics YOLO oriented-box (OBB) model trained on aerial
imagery (DOTA; classes "small vehicle" and "large vehicle"), run locally on Vexcel ortho tiles.

A second count beside Vexcel's built-in sam3 detector (VexcelClient.detect_cars_tiled), so the two can
be compared against a hand count and the usage index doesn't rest on one closed model.

Settings (.env):
    PARALLAX_YOLO_WEIGHTS  weights file or Ultralytics model name   (default yolo11s-obb.pt)
    PARALLAX_YOLO_CLASSES  comma-separated class names to count     (default small vehicle,large vehicle)
    PARALLAX_YOLO_CONF     confidence threshold                     (default 0.25)
    PARALLAX_YOLO_GSD_M    ground resolution tiles are resampled to (default 0.15 m/pixel)
    PARALLAX_YOLO_DEVICE   cpu | mps | cuda; empty = mps if available, else cpu

Ultralytics is AGPL-3.0: fine for a private hackathon repo; check the licence before a public or
commercial release. It is imported lazily, so the rest of the app and the tests don't need it.
"""
from __future__ import annotations

import io
import math
import os
import threading
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

WEIGHTS = os.environ.get("PARALLAX_YOLO_WEIGHTS", "yolo11s-obb.pt")
CLASSES = tuple(c.strip() for c in os.environ.get("PARALLAX_YOLO_CLASSES", "small vehicle,large vehicle").split(",") if c.strip())
CONF = float(os.environ.get("PARALLAX_YOLO_CONF", "0.25"))
GSD_M = float(os.environ.get("PARALLAX_YOLO_GSD_M", "0.15"))
DEVICE = os.environ.get("PARALLAX_YOLO_DEVICE", "")
DEDUPE_M = 1.5


# ---------------------------------------------------------------- geometry (pure, tested offline)
def metres_per_degree(lat: float) -> tuple[float, float]:
    """(metres per degree of longitude, metres per degree of latitude) at `lat`."""
    return 111_320.0 * math.cos(math.radians(lat)), 111_320.0


def pixel_to_lonlat(x: float, y: float, width: int, height: int, bounds: tuple) -> tuple[float, float]:
    """Pixel (x right, y down) in an image that covers `bounds` = (min_lon, min_lat, max_lon, max_lat)."""
    x0, y0, x1, y1 = bounds
    return x0 + (x / width) * (x1 - x0), y1 - (y / height) * (y1 - y0)


def lonlat_to_pixel(lon: float, lat: float, width: int, height: int, bounds: tuple) -> tuple[float, float]:
    x0, y0, x1, y1 = bounds
    return (lon - x0) / (x1 - x0) * width, (y1 - lat) / (y1 - y0) * height


def native_gsd(width_px: int, bounds: tuple) -> float:
    """Metres per pixel of an image `width_px` wide covering `bounds`."""
    mx, _ = metres_per_degree((bounds[1] + bounds[3]) / 2)
    return (bounds[2] - bounds[0]) * mx / width_px


def in_lot(cars: list[dict], lot) -> list[dict]:
    """Keep cars whose centre falls inside the lot polygon."""
    return [c for c in cars if lot.contains(Point(c["centre"]))]


def dedupe(cars: list[dict], metres: float = DEDUPE_M) -> list[dict]:
    """Drop a car whose centre is within `metres` of one already kept (seen by two tiles).
    Highest confidence first, so the better detection of a pair survives."""
    if not cars:
        return []
    mx, my = metres_per_degree(cars[0]["centre"][1])
    kept: list[dict] = []
    for c in sorted(cars, key=lambda c: -(c.get("confidence") or 0)):
        cx, cy = c["centre"]
        if any(abs(cx - k["centre"][0]) * mx < metres and abs(cy - k["centre"][1]) * my < metres for k in kept):
            continue
        kept.append(c)
    return kept


# ---------------------------------------------------------------- detector
@dataclass
class Box:
    """One detection in resized-image pixels: 4 corners (x, y), confidence, class name."""
    corners: list
    confidence: float
    label: str


class YoloDetector:
    """Loads the model once; detect() is safe to call from several threads (serialised by a lock)."""

    def __init__(self, weights: str = WEIGHTS, classes: tuple = CLASSES, conf: float = CONF,
                 gsd_m: float = GSD_M, device: str = DEVICE):
        self.weights, self.classes, self.conf, self.gsd_m, self.device = weights, classes, conf, gsd_m, device
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_version(self) -> str:
        try:
            import ultralytics
            v = ultralytics.__version__
        except ImportError:
            v = "?"
        return f"{os.path.basename(self.weights)}@ultralytics-{v};conf={self.conf};gsd={self.gsd_m}"

    def _load(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self.weights)
            if not self.device:
                try:
                    import torch
                    self.device = "mps" if torch.backends.mps.is_available() else "cpu"
                except Exception:
                    self.device = "cpu"
        return self._model

    def _predict(self, image) -> list[Box]:
        """Run the model on a PIL image; return boxes in that image's pixels."""
        m = self._load()
        side = max(image.width, image.height)
        imgsz = max(320, int(math.ceil(side / 32.0) * 32))
        r = m.predict(image, imgsz=imgsz, conf=self.conf, device=self.device, verbose=False)[0]
        out = []
        if r.obb is None:
            return out
        for corners, c, cls in zip(r.obb.xyxyxyxy.tolist(), r.obb.conf.tolist(), r.obb.cls.tolist()):
            name = m.names[int(cls)]
            if name in self.classes:
                out.append(Box(corners=corners, confidence=float(c), label=name))
        return out

    def detect(self, image_bytes: bytes, bounds: tuple) -> list[dict]:
        """Cars in one ortho tile covering `bounds` (min_lon, min_lat, max_lon, max_lat).
        Returns [{centre: (lon, lat), polygon: wkt, confidence, label}]."""
        from PIL import Image

        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w0, h0 = im.size
        scale = native_gsd(w0, bounds) / self.gsd_m          # e.g. 0.075 / 0.15 = 0.5
        w1, h1 = max(1, round(w0 * scale)), max(1, round(h0 * scale))
        if (w1, h1) != (w0, h0):
            im = im.resize((w1, h1), Image.LANCZOS)
        with self._lock:
            boxes = self._predict(im)
        cars = []
        for b in boxes:
            pts = [pixel_to_lonlat(x, y, w1, h1, bounds) for x, y in b.corners]
            poly = Polygon(pts)
            c = poly.centroid
            cars.append({"centre": (c.x, c.y), "polygon": poly.wkt, "confidence": round(b.confidence, 3), "label": b.label})
        return cars
