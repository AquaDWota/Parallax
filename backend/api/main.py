"""Parallax API.  Run:  cd backend && uvicorn api.main:app --reload --port 8000"""
from __future__ import annotations

import hashlib
import json
import random
from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from parallax import agent, config
from parallax.store import get_store
from parallax.tools import TOOLS_BY_NAME

app = FastAPI(title="Parallax")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@lru_cache(maxsize=1)
def _period_map() -> dict:
    """capture_id -> slider period: "2020-03" for synthetic captures, campaign year for real Vexcel ones."""
    c = get_store().captures
    if "period" in c.columns:
        return dict(zip(c.capture_id, c.period.astype(str)))
    return {cid: cid.split("-", 1)[1] for cid in c.capture_id}


def _period(capture_id: str) -> str:
    return _period_map().get(capture_id, "")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    s = get_store()
    periods = sorted({p for p in (_period(c) for c in s.captures.capture_id) if p})
    return dict(data_mode=config.DATA_MODE, agent_mode="llm" if agent.use_llm() else "scripted",
                cities=sorted(s.buildings.city.unique()), periods=periods,
                n_buildings=int(len(s.buildings)),
                n_measurable=int((s.buildings.parking_type == "surface").sum()))


@lru_cache(maxsize=64)
def _buildings_at(period: str, city: str | None) -> list[dict]:
    s = get_store()
    u = s.usage[s.usage.capture_id.map(_period) == period].sort_values("capture_date")
    # several collections can fall in one campaign year: prefer the latest usable one
    u = u.assign(_ok=u.status.eq("ok")).sort_values(["_ok", "capture_date"]).drop_duplicates("building_id", keep="last")
    u = u[["building_id", "index_smooth", "abs_index_smooth", "status", "cars"]]
    b = s.buildings if not city else s.buildings[s.buildings.city == city]
    m = b.merge(u, on="building_id", how="left")
    out = []
    for r in m.itertuples():
        out.append(dict(id=r.building_id, name=r.name, city=r.city, submarket=r.submarket,
                        lat=round(r.lat, 5), lon=round(r.lon, 5), type=r.property_type,
                        cls=r.building_class, parking=r.parking_type,
                        index=None if pd.isna(r.index_smooth) else round(float(r.index_smooth), 1),
                        abs_index=None if pd.isna(r.abs_index_smooth) else round(float(r.abs_index_smooth), 1),
                        status=r.status if isinstance(r.status, str) else "no_capture"))
    return out


@app.get("/api/buildings")
def buildings(period: str, city: str | None = None):
    return _buildings_at(period, city)


@app.get("/api/buildings/{building_id}")
def building(building_id: str):
    s = get_store()
    b = s.buildings[s.buildings.building_id == building_id]
    if b.empty:
        raise HTTPException(404, "unknown building")
    u = s.usage[s.usage.building_id == building_id].sort_values("capture_date")
    l = s.leases[s.leases.building_id == building_id].sort_values("expiry_date")
    rec = json.loads(b.iloc[0].to_json())
    rec["history"] = [dict(capture_id=r.capture_id, date=str(r.capture_date.date()),
                           index=None if pd.isna(r.index_smooth) else round(float(r.index_smooth), 1),
                           cars=None if pd.isna(r.cars) else int(r.cars), status=r.status) for r in u.itertuples()]
    rec["leases"] = [dict(tenant=r.tenant, industry=r.tenant_industry, sqft=int(r.sqft),
                          start=str(r.start_date.date()), expiry=str(r.expiry_date.date()), outcome=r.outcome)
                     for r in l.itertuples()]
    return rec


@app.get("/api/buildings/{building_id}/image")
def building_image(building_id: str, capture_id: str):
    """Real Vexcel crop if it has been fetched (data/imagery/<id>/<capture>.jpg), else a
    schematic lot drawn from the car count so the demo works on synthetic data."""
    real = config.DATA_DIR / "imagery" / building_id / f"{capture_id}.jpg"
    if real.exists():
        return FileResponse(real, media_type="image/jpeg")
    s = get_store()
    b = s.buildings[s.buildings.building_id == building_id]
    cc = s.car_counts[(s.car_counts.building_id == building_id) & (s.car_counts.capture_id == capture_id)]
    if b.empty or cc.empty:
        raise HTTPException(404, "no capture")
    return Response(_lot_svg(int(b.iloc[0].stall_capacity), cc.iloc[0].cars, cc.iloc[0].quality_flag,
                             f"{building_id}{capture_id}"), media_type="image/svg+xml")


def _lot_svg(capacity: int, cars, flag: str, seed: str) -> str:
    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))
    cols = 24
    rows = max(2, min(14, -(-capacity // cols)))
    w, h = 12, 22
    W, H = cols * (w + 2) + 40, rows * (h + 10) + 90
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
             f'<rect width="{W}" height="{H}" fill="#3b3f3a"/>',
             f'<rect x="10" y="10" width="{W - 20}" height="40" fill="#8a8c84"/>',
             f'<text x="{W / 2}" y="36" font-family="sans-serif" font-size="13" text-anchor="middle" fill="#2a2a2a">building</text>']
    stalls = [(20 + c * (w + 2), 64 + r * (h + 10)) for r in range(rows) for c in range(cols)][:capacity]
    for x, y in stalls:
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#d9d6c8" stroke-width="0.6" opacity="0.6"/>')
    n = 0 if cars is None or pd.isna(cars) else int(cars)
    palette = ["#e8e6e1", "#1c1c1c", "#9aa3ab", "#7b2d26", "#2c4a6b", "#c9c2b2"]
    for x, y in rng.sample(stalls, min(n, len(stalls))):
        parts.append(f'<rect x="{x + 1.5}" y="{y + 2}" width="{w - 3}" height="{h - 4}" rx="2" fill="{rng.choice(palette)}"/>')
    if flag in ("cloud", "shadow"):
        parts.append(f'<rect width="{W}" height="{H}" fill="{"#ffffff" if flag == "cloud" else "#000000"}" opacity="0.55"/>')
    parts.append("</svg>")
    return "".join(parts)


@lru_cache(maxsize=1)
def _overview() -> dict:
    t = TOOLS_BY_NAME
    return dict(
        bins=json.loads(t["usage_vs_renewal"]()),
        bins_major=json.loads(t["usage_vs_renewal"](min_lease_share=0.25)),
        regression=json.loads(t["regression"]()),
        regional=json.loads(t["regional_series"](level="city")),
    )


@app.get("/api/results/overview")
def overview():
    return _overview()


class AskBody(BaseModel):
    question: str
    history: list[dict] | None = None


@app.post("/api/ask")
async def ask(body: AskBody):
    async def stream():
        async for ev in agent.ask(body.question, body.history):
            yield f"data: {json.dumps(ev, default=str)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/tools/{name}")
def call_tool(name: str, args: dict | None = None):
    """Run one analysis tool directly (used by the UI, e.g. clicking a usage bin)."""
    if name not in TOOLS_BY_NAME:
        raise HTTPException(404, f"unknown tool {name}")
    try:
        return json.loads(TOOLS_BY_NAME[name](**(args or {})))
    except TypeError as e:
        raise HTTPException(400, str(e))
