"""Preview what dropping roads does to each lot outline, before recounting anything.

For every building's current lot (data/real/vexcel_buildings.csv) it fetches the parcels around it, keeps only
the part of the lot inside some parcel (streets belong to none), and reports how much of the lot that removes.
Nothing in vexcel_buildings.csv or car_counts.csv is changed: the recount does that.

    cd backend
    python -m scripts.clip_lots                       # all buildings in study_buildings_v3.csv (~1 call each)
    python -m scripts.clip_lots --draw P246877 P252391  # before/after pictures: red = old outline, yellow = new

Writes
  data/real/lot_clip_report.csv     building, old and new lot area, share kept
  data/real/recount_after_clip.csv  study rows for buildings that lose 10%+ of their lot - recount these with
                                    python -m scripts.batch_car_counts --buildings ../data/real/recount_after_clip.csv --redo --workers 3 --tile-m 70
  vexcel_output/lot_clip/<id>.jpg   with --draw
"""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from shapely import wkt as swkt
from shapely.ops import transform

from parallax.lots import _to_m, clip_to_parcels
from parallax.vexcel import VexcelClient
from scripts.batch_car_counts import parcels_in

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "data" / "real"
SHRINK = 0.90   # recount buildings that keep less than 90% of their lot


def _rows(path: Path) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def area_m2(g) -> float:
    return transform(_to_m(g.centroid.y)[0], g).area


def clip_one(c: VexcelClient, bid: str, lot_wkt: str):
    lot = swkt.loads(lot_wkt)
    x0, y0, x1, y1 = lot.bounds
    feats = parcels_in(c, f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))")
    new, kept = clip_to_parcels(lot, feats or [])
    return dict(building_id=bid, old_m2=round(area_m2(lot)), new_m2=round(area_m2(new)),
                kept_share=kept if kept is not None else "", parcels=len(feats or []),
                note="no parcel data - unchanged" if kept is None else ("no real lot (mostly street) - will be not measurable" if kept < 0.3 else "")), lot, new


def draw(c: VexcelClient, bid: str, lot, new, out: Path):
    """Plain ortho of the area, with the outlines drawn here: red = old lot, yellow = lot without streets.
    (Vexcel's own drawing option fails on long outlines.)"""
    import io
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = lot.buffer(0.0002).bounds
    box = f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"
    im = Image.open(io.BytesIO(c.ortho(box, dims="900,900"))).convert("RGB")
    w, h = im.size
    px = lambda x, y: ((x - x0) / (x1 - x0) * w, (y1 - y) / (y1 - y0) * h)
    d = ImageDraw.Draw(im)
    for geom, color, width in ((lot, (229, 72, 59), 5), (new, (242, 194, 48), 3)):
        for poly in getattr(geom, "geoms", [geom]):
            for ring in [poly.exterior, *poly.interiors]:
                d.line([px(x, y) for x, y in ring.coords], fill=color, width=width, joint="curve")
    d.rectangle([0, 0, 330, 26], fill=(0, 0, 0))
    d.text((8, 7), f"{bid}  red: old lot   yellow: without streets", fill=(255, 255, 255))
    out.mkdir(parents=True, exist_ok=True)
    im.save(out / f"{bid}.jpg", quality=90)
    return out / f"{bid}.jpg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buildings", default=str(REAL / "study_buildings_v3.csv"))
    ap.add_argument("--draw", nargs="*", default=None, help="building ids to picture (skips the report)")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    lots = {r["building_id"]: r["lot_wkt"] for r in _rows(REAL / "vexcel_buildings.csv")}  # last row wins
    c = VexcelClient()

    if a.draw is not None:
        for bid in a.draw:
            if bid not in lots:
                print(f"{bid}: no lot in vexcel_buildings.csv")
                continue
            r, lot, new = clip_one(c, bid, lots[bid])
            path = draw(c, bid, lot, new, ROOT / "vexcel_output" / "lot_clip")
            print(f"{bid}: lot {r['old_m2']:,} -> {r['new_m2']:,} m2 (kept {r['kept_share'] or 'all'}) -> {path}")
        return

    study = _rows(Path(a.buildings))
    todo = [b for b in study if b["building_id"] in lots]
    print(f"checking {len(todo)} lots against parcel boundaries, {a.workers} at a time")
    report = []
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(clip_one, c, b["building_id"], lots[b["building_id"]]): b for b in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                report.append(f.result()[0])
            except Exception as e:
                report.append(dict(building_id=futs[f]["building_id"], old_m2="", new_m2="", kept_share="", parcels="", note=f"error: {str(e)[:80]}"))
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}")

    with open(REAL / "lot_clip_report.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["building_id", "old_m2", "new_m2", "kept_share", "parcels", "note"])
        w.writeheader()
        w.writerows(sorted(report, key=lambda r: r["building_id"]))
    shrunk = {r["building_id"] for r in report if r["kept_share"] != "" and float(r["kept_share"]) < SHRINK}
    no_lot = [r["building_id"] for r in report if r["kept_share"] != "" and float(r["kept_share"]) < 0.3]
    with open(REAL / "recount_after_clip.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(study[0].keys()))
        w.writeheader()
        w.writerows([b for b in study if b["building_id"] in shrunk])

    kept = sorted(float(r["kept_share"]) for r in report if r["kept_share"] != "")
    med = kept[len(kept) // 2] if kept else None
    print(f"\n{len(kept)} lots clipped, median share kept {med:.0%}" if med is not None else "\nno lots clipped")
    print(f"{len(shrunk)} lose 10%+ of their lot -> data/real/recount_after_clip.csv")
    print(f"{len(no_lot)} have no real lot (under 30% left) and will become not measurable: {', '.join(no_lot[:10])}")
    print("worst:", ", ".join(f"{r['building_id']} {float(r['kept_share']):.0%}" for r in sorted(
        (r for r in report if r["kept_share"] != ""), key=lambda r: float(r["kept_share"]))[:8]))


if __name__ == "__main__":
    main()
