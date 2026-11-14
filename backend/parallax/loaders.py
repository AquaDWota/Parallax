"""Real-data loader: CoStar (via scripts.prepare_costar) + Vexcel car counts (via
scripts.batch_car_counts). Returns the same four tables as the synthetic generator.

Files in data/real/ (git-ignored):
  costar_properties.csv   prepare_costar   type, class, RBA, submarket, surface stalls, parking type
  costar_leases.csv       prepare_costar   lease expiries with outcomes
  vexcel_buildings.csv    batch            lot polygon area and stall estimate per imaged building
  captures.csv            batch            one row per Vexcel collection (capture_id = collection name)
  car_counts.csv          batch            cars per building per collection

Buildings = every imaged building: CoStar properties (P<id>) plus discovered neighbours (V-...),
which have no leases but improve the peer comparison.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import config

REAL_DIR = config.DATA_DIR / "real"

INDUSTRY = {0: "unknown", 1: "accounting", 2: "transportation", 3: "engineering", 4: "real_estate",
            5: "manufacturing", 6: "retail", 7: "finance", 8: "tech", 9: "government", 10: "construction",
            11: "information", 12: "professional_services", 13: "personal_services", 14: "insurance",
            15: "healthcare", 16: "legal", 17: "hospitality", 18: "admin_support", 19: "agriculture",
            20: "arts", 21: "education", 22: "management", 23: "energy", 24: "rental_leasing",
            25: "utilities", 26: "waste", 27: "wholesale"}


def capture_period(capture_id: str, capture_date) -> str:
    """Vexcel campaigns are named by year (us-tx-houston-2026 was flown Dec 2025): use that year."""
    m = re.search(r"(\d{4})$", str(capture_id))
    return m.group(1) if m else str(pd.Timestamp(capture_date).year)


def load_real():
    props = pd.read_csv(REAL_DIR / "costar_properties.csv")
    vb = pd.read_csv(REAL_DIR / "vexcel_buildings.csv").drop_duplicates("building_id", keep="last")
    caps = pd.read_csv(REAL_DIR / "captures.csv", parse_dates=["capture_date"]).drop_duplicates("capture_id")
    cc = pd.read_csv(REAL_DIR / "car_counts.csv").drop_duplicates(["building_id", "capture_id"], keep="last")
    leases = pd.read_csv(REAL_DIR / "costar_leases.csv", parse_dates=["start_date", "expiry_date"])

    imaged = set(cc.building_id)
    # ---------- buildings ----------
    p = props[props.building_id.isin(imaged)].copy()
    p = p.merge(vb[["building_id", "stall_capacity_est", "lot_area_m2"]], on="building_id", how="left")
    sq = pd.to_numeric(p["rba_sqft"], errors="coerce").fillna(pd.to_numeric(p["max_tenant_sqft"], errors="coerce"))
    surface = pd.to_numeric(p["surface_spaces"], errors="coerce")
    cap = surface.where(surface >= 10, p["stall_capacity_est"])
    pb = pd.DataFrame(dict(
        building_id=p.building_id, name=p.address, city=p.city,
        submarket=("SM " + p.submarket_id.astype("Int64").astype(str)).where(p.submarket_id.notna(), p.postcode.astype(str)),
        lat=p.lat, lon=p.lon, property_type=p.property_type.fillna("unknown").replace("", "unknown"),
        building_class=p.building_class.fillna("U").replace("", "U"), sqft=sq.fillna(50000.0),
        year_built=pd.to_numeric(p.year_built, errors="coerce"),
        # mixed surface+garage lots are measured; the detail is kept for slicing
        parking_type=np.where(p.parking_type.isin(["surface", "mixed", "unknown"]), "surface", "structured"),
        parking_detail=p.parking_type, stall_capacity=cap.fillna(50).clip(lower=10).astype(int),
    ))
    v = vb[vb.building_id.str.startswith("V-") & vb.building_id.isin(imaged)]
    vbld = pd.DataFrame(dict(
        building_id=v.building_id, name="(neighbour) " + v.area.fillna("").astype(str), city=v.city,
        submarket=v.area.fillna(v.city).astype(str), lat=v.lat, lon=v.lon, property_type="unknown",
        building_class="U", sqft=(v.footprint_m2.fillna(2000) * 10.764).clip(lower=5000),
        year_built=np.nan, parking_type="surface", parking_detail="discovered",
        stall_capacity=v.stall_capacity_est.fillna(50).clip(lower=10).astype(int),
    ))
    buildings = pd.concat([pb, vbld], ignore_index=True)

    # ---------- captures ----------
    captures = caps[["capture_id", "city", "capture_date"]].copy()
    captures["period"] = [capture_period(c, d) for c, d in zip(captures.capture_id, captures.capture_date)]
    captures["holiday"] = caps["holiday"].fillna(0).astype(int).to_numpy()

    # ---------- car counts ----------
    car_counts = cc[cc.building_id.isin(buildings.building_id)][["building_id", "capture_id", "cars", "quality_flag"]].copy()
    car_counts["cars"] = pd.to_numeric(car_counts["cars"], errors="coerce")
    car_counts.loc[car_counts.quality_flag.isin(["no_image", "error"]), "quality_flag"] = "no_image"
    # a building whose newest lot was empty (batch pre-check) is treated like a garage building
    nm = set(car_counts.loc[car_counts.quality_flag == "not_measurable", "building_id"])
    buildings.loc[buildings.building_id.isin(nm), "parking_type"] = "structured"
    garage = set(buildings.loc[buildings.parking_type != "surface", "building_id"])
    car_counts.loc[car_counts.building_id.isin(garage), ["cars", "quality_flag"]] = [np.nan, "not_measurable"]

    # A 0 on a lot that normally holds 15+ cars is a collection that doesn't really cover the lot
    # (e.g. one Oct-2016 collection says 0 where another flown the same day says 306), not an empty lot.
    ok = car_counts.quality_flag.eq("ok") & car_counts.cars.notna()
    typical = car_counts[ok].groupby("building_id").cars.median()
    zero = ok & car_counts.cars.eq(0) & car_counts.building_id.map(typical).ge(15)
    car_counts.loc[zero, "quality_flag"] = "suspect_zero"

    # Capacity: the largest of CoStar's surface stalls, the lot-size estimate, and the busiest count seen.
    # (CoStar has no stall count for many industrial buildings; a default of 50-100 gave fills of 170%.)
    busiest = car_counts[car_counts.quality_flag.eq("ok")].groupby("building_id").cars.quantile(0.95)
    est = vb.set_index("building_id")["stall_capacity_est"]
    cap = buildings.set_index("building_id")["stall_capacity"].astype(float)
    cap = np.maximum(cap, est.reindex(cap.index).fillna(0))
    cap = np.maximum(cap, (1.1 * busiest).reindex(cap.index).fillna(0))
    buildings["stall_capacity"] = buildings.building_id.map(cap).fillna(50).clip(lower=10).round().astype(int)

    # ---------- leases ----------
    l = leases[leases.building_id.isin(pb.building_id)].copy()
    leases_out = pd.DataFrame(dict(
        lease_id=l.lease_id.astype(str), building_id=l.building_id, tenant=l.tenant.fillna("Unknown tenant"),
        tenant_industry=pd.to_numeric(l.tenant_industry, errors="coerce").map(INDUSTRY).fillna("unknown"),
        sqft=pd.to_numeric(l.sqft, errors="coerce").fillna(0).clip(lower=100),
        start_date=l.start_date, expiry_date=l.expiry_date, outcome=l.outcome,
        rent_psf=pd.to_numeric(l.rent_psf, errors="coerce"),
    ))
    leases_out["rent_psf"] = leases_out["rent_psf"].where(leases_out["rent_psf"] > 0)
    leases_out["rent_psf"] = leases_out["rent_psf"].fillna(leases_out["rent_psf"].median() if leases_out["rent_psf"].notna().any() else 25.0)
    return buildings, captures, car_counts, leases_out


def load_tenancies(building_ids) -> pd.DataFrame:
    """Every CoStar tenancy at the imaged properties (for building occupancy over time)."""
    t = pd.read_csv(REAL_DIR / "costar_occupancy.csv", parse_dates=["from_date", "to_date"])
    t = t[t.building_id.isin(set(building_ids))]
    return t[["building_id", "from_date", "to_date", "sqft"]].reset_index(drop=True)


def load_upcoming(building_ids) -> pd.DataFrame:
    """Current CoStar leases expiring after today (for the renewal-risk column of the screen)."""
    f = REAL_DIR / "costar_upcoming.csv"
    if not f.exists():
        return pd.DataFrame(columns=["building_id", "tenant", "tenant_industry", "sqft", "expiry_date"])
    t = pd.read_csv(f, parse_dates=["expiry_date"])
    t = t[t.building_id.isin(set(building_ids))].copy()
    t["tenant_industry"] = pd.to_numeric(t.tenant_industry, errors="coerce").map(INDUSTRY).fillna("unknown")
    return t.reset_index(drop=True)
