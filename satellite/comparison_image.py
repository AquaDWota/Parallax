"""The same parking lot at three sharpnesses: Vexcel 7.5 cm, NAIP 60 cm, Sentinel-2 10 m.

    python comparison_image.py
        -> results/comparison_public.png   NAIP + Sentinel-2 only (free public data, safe to commit)
    python comparison_image.py --vexcel path/to/239748_collection_us-tx-houston-2023.jpg
        -> private/comparison_with_vexcel.png   adds the Vexcel panel. For slides ONLY: Vexcel
           imagery is licensed for the event, and private/ is git-ignored.
"""
import math
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from PIL import Image, ImageDraw, ImageFont
from rasterio.transform import from_bounds as tfb
from rasterio.warp import Resampling, reproject, transform_bounds

HERE = Path(__file__).resolve().parent
LAT, LON, HALF = 29.6794344, -95.4207655, 60  # 2646 Loop, Houston: 120 m view
dlat = HALF / 111_320
dlon = HALF / (111_320 * math.cos(math.radians(LAT)))
B = (LON - dlon, LAT - dlat, LON + dlon, LAT + dlat)
SIZE = 640


def grab(hrefs, px, scale=None, offset=0):
    """Reproject the view to a px x px UTM grid with nearest-neighbour, so real pixels stay visible."""
    db = transform_bounds("EPSG:4326", "EPSG:32615", *B)
    T = tfb(*db, px, px)
    out = np.zeros((3, px, px), float)
    for band, (href, idx) in enumerate(hrefs):
        with rasterio.open(href) as src:
            reproject(rasterio.band(src, idx), out[band], dst_transform=T, dst_crs="EPSG:32615",
                      resampling=Resampling.nearest)
    if scale:
        out = np.clip((out - offset) / scale, 0, 1) * 255
    return Image.fromarray(out.transpose(1, 2, 0).astype(np.uint8)).resize((SIZE, SIZE), Image.NEAREST)


def font(size, bold=False):
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    try:
        return ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{name}", size)
    except OSError:
        return ImageFont.load_default()


def main():
    vexcel = sys.argv[sys.argv.index("--vexcel") + 1] if "--vexcel" in sys.argv else None
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    n = next(iter(cat.search(collections=["naip"], bbox=B, datetime="2022-01-01/2022-12-31").items()))
    naip = grab([(n.assets["image"].href, i) for i in (1, 2, 3)], 200)
    s = next(iter(cat.search(collections=["sentinel-2-l2a"], bbox=B, datetime="2023-01-23/2023-01-23").items()))
    off = 1000 if float(s.properties.get("s2:processing_baseline", "0")) >= 4 else 0
    s2 = grab([(s.assets[k].href, 1) for k in ("B04", "B03", "B02")], 12, scale=2500, offset=off)

    panels = []
    if vexcel:
        panels.append((Image.open(vexcel).convert("RGB").resize((SIZE, SIZE), Image.LANCZOS),
                       "Vexcel aerial · 7.5 cm", "Each car ~60 x 24 pixels → cars counted"))
    panels += [(naip, "NAIP aerial · 60 cm", "Each car ~7 x 3 pixels → small blobs"),
               (s2, "Sentinel-2 satellite · 10 m", "Whole lot ~120 pixels → no cars visible")]

    W, H = SIZE * len(panels) + 20 * (len(panels) + 1), SIZE + 230
    canvas = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(canvas)
    d.text((20, 18), "Same parking lot, different sharpness (2646 Loop, Houston office: 120 m view)",
           font=font(34, True), fill=(20, 20, 20))
    for k, (img, title, sub) in enumerate(panels):
        x = 20 + k * (SIZE + 20)
        canvas.paste(img, (x, 80))
        d.text((x, 80 + SIZE + 14), title, font=font(34, True), fill=(20, 20, 20))
        d.text((x, 80 + SIZE + 58), sub, font=font(24), fill=(70, 70, 70))
    credit = "USDA NAIP (2022) · Copernicus Sentinel-2 (23 Jan 2023), via Microsoft Planetary Computer"
    if vexcel:
        credit = "Vexcel Imaging US (Jan 2023) · " + credit
    d.text((20, H - 40), "Imagery: " + credit, font=font(24), fill=(110, 110, 110))

    out_dir = HERE / ("private" if vexcel else "results")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / ("comparison_with_vexcel.png" if vexcel else "comparison_public.png")
    canvas.save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
