"""Building screen: where the lease record and the parking lot disagree, in either direction.

Per measurable building with a pre-COVID baseline and at least one capture since 2023:
  leased_pre      CoStar occupancy (tenant sq ft / building size), median over pre-COVID captures, %
  leased_now      CoStar occupancy today, %
  parking_now     lot fill since 2023 as % of the building's own pre-COVID fill (median of captures)
  gap             min(leased_now - leased_pre, +10) - (parking_now - 100): how much more the lot emptied than
                  the lease record did, in points. High = shadow vacancy. Leasing gains count up to +10 only:
                  a jump from 20% to 98% leased usually means CoStar's older tenant history is incomplete.
  rollover_24m    share of the building's leased sq ft whose lease expires in the next 24 months
  watch           risk flag: leased within 5 points of pre-COVID but parking under 70% of pre-COVID
  opportunity_score  the mirror of gap: (parking_now - 100) - min(leased_change, +10). High = the lot is busier
                  than the lease record suggests.
  opportunity     opportunity flag: lot at or above its pre-COVID level while leasing is no more than 5 points
                  up and under 90% leased - demand in the building is running ahead of its leases.
Risk: space that is leased but unused is the space most likely to go dark at renewal, so risk-flagged buildings
with large rollover deserve the first look. Opportunity: a busy lot with room left to lease points to demand the
lease record hasn't caught up with - lease-up upside, or tenants CoStar hasn't recorded yet (worth checking).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .occupancy import occupancy_at

TODAY = pd.Timestamp("2026-11-01")
RECENT_FROM = pd.Timestamp("2023-01-01")
PRE_COVID_END = pd.Timestamp("2020-03-01")


def build_screen(buildings: pd.DataFrame, usage: pd.DataFrame, tenancies: pd.DataFrame,
                 upcoming: pd.DataFrame | None) -> pd.DataFrame:
    has_ten = set(tenancies.building_id)
    u = usage[usage.abs_index.notna() & usage.building_id.isin(has_ten)].copy()
    size = buildings.set_index("building_id")["sqft"]
    u["occ"] = occupancy_at(tenancies, size, pd.DataFrame(dict(building_id=u.building_id, date=u.capture_date)))
    pre = u[u.capture_date < PRE_COVID_END].groupby("building_id").agg(leased_pre=("occ", "median"),
                                                                         n_pre=("occ", "size"))
    rec = u[u.capture_date >= RECENT_FROM].groupby("building_id").agg(parking_now=("abs_index", "median"),
                                                                        n_recent=("abs_index", "size"),
                                                                        last_capture=("capture_date", "max"))
    d = pre.join(rec, how="inner")
    if d.empty:
        return d
    now = pd.DataFrame(dict(building_id=d.index, date=TODAY))
    d["leased_now"] = occupancy_at(tenancies, size, now)
    d["leased_change"] = d.leased_now - d.leased_pre
    d["parking_change"] = d.parking_now - 100
    d["gap"] = d.leased_change.clip(upper=10) - d.parking_change
    d["opportunity_score"] = -d.gap

    # renewal risk ahead
    d["rollover_24m"] = 0.0
    d["expiring_tenants"] = ""
    if upcoming is not None and len(upcoming):
        up = upcoming[(upcoming.expiry_date > TODAY) & (upcoming.expiry_date <= TODAY + pd.DateOffset(months=24))]
        leased_sqft = (d.leased_now / 100 * size.reindex(d.index)).clip(lower=1)
        exp = up.groupby("building_id").sqft.sum()
        d["rollover_24m"] = (exp.reindex(d.index).fillna(0) / leased_sqft).clip(upper=1.0) * 100
        top = (up.sort_values("sqft", ascending=False).groupby("building_id")
               .apply(lambda g: "; ".join(f"{r.tenant} ({int(r.sqft):,} sf, {r.expiry_date:%b %Y})"
                                          for r in g.head(3).itertuples())))
        d["expiring_tenants"] = top.reindex(d.index).fillna("")

    # CoStar occupancy that computes to ~0% or well over 100% means incomplete tenant records
    # or that moves 40+ points either way means incomplete tenant records: shown, flagged, never flagged as
    # risk or opportunity
    d["data_check"] = (d.leased_pre < 20) | (d.leased_pre > 110) | (d.leased_now > 110) | (d.leased_change.abs() > 40)
    d["watch"] = (d.leased_change >= -5) & (d.parking_now <= 70) & ~d.data_check
    d["opportunity"] = (d.parking_now >= 100) & (d.leased_change <= 5) & (d.leased_now < 90) & ~d.data_check
    b = buildings.set_index("building_id")
    for col in ["name", "city", "submarket", "property_type", "building_class", "lat", "lon", "sqft"]:
        d[col] = b[col].reindex(d.index)
    d = d.reset_index().rename(columns={"index": "building_id"})
    # risk flags first (by gap), then opportunity flags (by opportunity score), then everything else
    d["_order"] = np.where(d.watch, 0, np.where(d.opportunity, 1, 2))
    d["_key"] = np.where(d.opportunity & ~d.watch, d.opportunity_score, d.gap)
    d = d.sort_values(["_order", "_key", "rollover_24m"], ascending=[True, False, False]).drop(columns=["_order", "_key"]).reset_index(drop=True)
    d["rank"] = np.arange(1, len(d) + 1)
    return d


def summary(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"n": 0}
    ok = d[~d.data_check]
    w = d[d.watch]
    return dict(
        n=int(len(d)), n_clean=int(len(ok)), n_watch=int(len(w)),
        share_watch=round(float(len(w) / max(len(ok), 1)), 3),
        median_leased_change=round(float(ok.leased_change.median()), 1),
        median_parking_now=round(float(ok.parking_now.median()), 1),
        watch_rollover_sqft_share=round(float(w.rollover_24m.median()), 1) if len(w) else None,
        watch_with_rollover=int((w.rollover_24m >= 10).sum()),
        n_opportunity=int(d.opportunity.sum()),
        share_opportunity=round(float(d.opportunity.sum() / max(len(ok), 1)), 3),
    )
