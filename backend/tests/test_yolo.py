"""YOLO detector path, offline: no Vexcel key, no network, no model weights (N7).
A synthetic tile stands in for a Vexcel ortho; the model and the client are mocked."""
import csv
import io

import pytest
from PIL import Image
from shapely.geometry import Polygon, box

from parallax import yolo
from parallax.yolo import (Box, YoloDetector, dedupe, in_lot, lonlat_to_pixel, metres_per_degree, native_gsd,
                           pixel_to_lonlat)
from scripts.batch_yolo_counts import OUT_COLS, count_pair, grid_tiles, run

LAT, LON = 29.73, -95.56
MX, MY = metres_per_degree(LAT)
TILE = (LON, LAT, LON + 60 / MX, LAT + 60 / MY)            # a 60 m tile


def tile_jpeg(px: int = 800) -> bytes:
    """Stand-in for a Vexcel ortho: 800 px across 60 m = 7.5 cm/pixel, Vexcel's urban resolution."""
    buf = io.BytesIO()
    Image.new("RGB", (px, px), (90, 90, 90)).save(buf, "JPEG")
    return buf.getvalue()


def test_pixel_mapping_corners_and_centre():
    w = h = 800
    assert pixel_to_lonlat(0, 0, w, h, TILE) == pytest.approx((TILE[0], TILE[3]))       # top-left = NW
    assert pixel_to_lonlat(w, h, w, h, TILE) == pytest.approx((TILE[2], TILE[1]))       # bottom-right = SE
    lon, lat = pixel_to_lonlat(400, 400, w, h, TILE)
    assert lonlat_to_pixel(lon, lat, w, h, TILE) == pytest.approx((400, 400))
    assert native_gsd(800, TILE) == pytest.approx(0.075, rel=1e-3)


class FakeDetector(YoloDetector):
    """Returns one 'car' at a fixed fraction of whatever (resized) image it gets."""

    def __init__(self, frac=(0.5, 0.5), **kw):
        super().__init__(**kw)
        self.frac, self.sizes = frac, []

    def _predict(self, image):
        self.sizes.append(image.size)
        cx, cy = self.frac[0] * image.width, self.frac[1] * image.height
        return [Box(corners=[(cx - 8, cy - 15), (cx + 8, cy - 15), (cx + 8, cy + 15), (cx - 8, cy + 15)],
                    confidence=0.8, label="small vehicle")]

    @property
    def model_version(self):
        return f"fake;conf={self.conf}"


def test_detect_resamples_to_gsd_and_maps_to_lonlat():
    det = FakeDetector(gsd_m=0.15)
    cars = det.detect(tile_jpeg(800), TILE)
    assert det.sizes == [(400, 400)]                       # 7.5 cm -> 15 cm halves the image
    (c,) = cars
    assert c["centre"] == pytest.approx(((TILE[0] + TILE[2]) / 2, (TILE[1] + TILE[3]) / 2), abs=1e-7)
    assert Polygon.__name__ in type(__import__("shapely").wkt.loads(c["polygon"])).__name__


def test_lot_clipping_and_dedupe():
    lot = box(TILE[0], TILE[1], (TILE[0] + TILE[2]) / 2, TILE[3])          # west half of the tile
    inside = {"centre": (TILE[0] + 10 / MX, LAT + 30 / MY), "confidence": 0.9}
    outside = {"centre": (TILE[2] - 10 / MX, LAT + 30 / MY), "confidence": 0.9}
    assert in_lot([inside, outside], lot) == [inside]
    near = {"centre": (inside["centre"][0] + 1.0 / MX, inside["centre"][1]), "confidence": 0.5}   # 1 m away
    far = {"centre": (inside["centre"][0] + 3.0 / MX, inside["centre"][1]), "confidence": 0.5}    # 3 m away
    kept = dedupe([near, inside, far])
    assert inside in kept and far in kept and near not in kept and len(kept) == 2


def test_grid_tiles_are_fixed_and_shared():
    a = box(LON, LAT, LON + 100 / MX, LAT + 30 / MY)
    b = box(LON + 50 / MX, LAT, LON + 150 / MX, LAT + 30 / MY)
    ka, kb = {k for k, _ in grid_tiles(a, 60)}, {k for k, _ in grid_tiles(b, 60)}
    assert ka & kb                                           # overlapping lots reuse the same tile files
    for _, bd in grid_tiles(a, 60):
        assert (bd[2] - bd[0]) * MX == pytest.approx(60, rel=0.01)


class FakeClient:
    """ortho_with_size returns the stand-in tile; collection 'empty' has no imagery (404)."""

    def __init__(self):
        self.calls = 0

    def ortho_with_size(self, wkt, collection=None, dims=None, image_format="jpeg"):
        self.calls += 1
        if image_format == "png":  # pretend this API refuses PNG: the batch must fall back to JPEG
            raise RuntimeError("/ortho/extract failed (400): unsupported image-format")
        if collection == "empty":
            raise RuntimeError("/ortho/extract failed (404): No image matching the provided parameters found")
        return tile_jpeg(800), (800, 800)


def test_batch_end_to_end_resume_and_cache(tmp_path):
    real, cache = tmp_path / "real", tmp_path / "tiles"
    real.mkdir()
    lot = box(LON, LAT, LON + 50 / MX, LAT + 50 / MY)
    with open(real / "vexcel_buildings.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "lot_wkt"])
        w.writerow(["P1", lot.wkt])
        w.writerow(["P2", lot.wkt])
    with open(real / "car_counts.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "capture_id", "cars", "quality_flag", "mean_conf"])
        w.writerows([["P1", "c2022", 10, "ok", ""], ["P1", "empty", "", "ok", ""],
                     ["P2", "c2022", "", "not_measurable", ""]])
    client, det = FakeClient(), FakeDetector()
    run(real, cache, client, det, workers=1, log=lambda *_: None)
    rows = list(csv.DictReader(open(real / "car_counts_yolo.csv")))
    assert list(rows[0].keys()) == OUT_COLS
    got = {(r["building_id"], r["capture_id"]): r for r in rows}
    assert set(got) == {("P1", "c2022"), ("P1", "empty")}           # garage pair skipped by default
    assert got[("P1", "empty")]["quality_flag"] == "no_image"
    assert got[("P1", "c2022")]["quality_flag"] == "ok" and int(got[("P1", "c2022")]["cars"]) >= 1
    assert got[("P1", "c2022")]["detector"] == "yolo"
    calls = client.calls
    run(real, cache, client, det, workers=1, log=lambda *_: None)    # resume: nothing left to do
    assert client.calls == calls
    assert len(list(csv.DictReader(open(real / "car_counts_yolo.csv")))) == 2
    # new settings -> everything is recounted, from cached tiles only
    det2 = FakeDetector(conf=0.05)
    run(real, cache, client, det2, workers=1, log=lambda *_: None)
    assert client.calls == calls
    rows = list(csv.DictReader(open(real / "car_counts_yolo.csv")))
    assert len(rows) == 4 and rows[-1]["model_version"] == det2.model_version
    # tiles are cached: counting the same pair again makes no API calls
    count_pair(client, det, cache, lot, "c2022", 60)
    count_pair(client, det, cache, lot, "empty", 60)
    assert client.calls == calls


def test_ultralytics_not_needed_to_import():
    """The app, the batch and the comparison import without loading ultralytics (it loads on first detect)."""
    import subprocess
    import sys
    code = ("import sys, parallax.yolo, scripts.batch_yolo_counts, scripts.compare_detectors, parallax.loaders; "
            "print('ultralytics' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
