"""Lease-event table: one row per lease expiry, with what the tenant did and the
building's parking usage before it."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

KEPT = {"renewed", "expanded"}


def build_lease_events(buildings: pd.DataFrame, leases: pd.DataFrame, usage: pd.DataFrame,
                       lead_months: int = 0,
                       window_months: int = config.PREDICTOR_WINDOW_MONTHS,
                       min_expiry: str = "2019-03-01", max_expiry: str = "2026-10-01") -> tuple[pd.DataFrame, dict]:
    """Return (events, exclusions).

    usage    = mean smoothed index over the `window_months` ending `lead_months` before expiry
    trend    = slope of the index over the last 4 captures in that window's lookback (points/capture)
    """
    ev = leases[(leases.expiry_date >= min_expiry) & (leases.expiry_date < max_expiry)].copy()
    ev = ev.merge(buildings[["building_id", "city", "submarket", "property_type", "building_class",
                             "sqft", "parking_type", "lat", "lon", "name"]]
                  .rename(columns={"sqft": "building_sqft"}), on="building_id")
    excl = {"total_expiries": int(len(ev))}

    garage = ev.parking_type != "surface"
    excl["garage_not_measurable"] = int(garage.sum())
    ev = ev[~garage]

    series = {bid: (g["capture_date"].to_numpy(), g["index_smooth"].to_numpy())
              for bid, g in usage[usage.status.eq("ok") | usage.index_smooth.notna()]
              .sort_values("capture_date").groupby("building_id")}

    use, trend, ncap = [], [], []
    for r in ev.itertuples():
        dates, vals = series.get(r.building_id, (np.array([], dtype="datetime64[ns]"), np.array([])))
        end = np.datetime64(r.expiry_date - pd.DateOffset(months=lead_months))
        start = np.datetime64(r.expiry_date - pd.DateOffset(months=lead_months + window_months))
        m = (dates >= start) & (dates < end) & ~np.isnan(vals)
        use.append(np.nanmean(vals[m]) if m.any() else np.nan)
        ncap.append(int(m.sum()))
        prior = (dates < end) & ~np.isnan(vals)
        v = vals[prior][-4:]
        trend.append(np.polyfit(np.arange(len(v)), v, 1)[0] if len(v) >= 3 else np.nan)
    ev["usage"] = use
    ev["trend"] = trend
    ev["n_captures"] = ncap

    no_img = ev["usage"].isna()
    excl["no_usable_imagery"] = int(no_img.sum())
    ev = ev[~no_img].copy()
    ev["trend"] = ev["trend"].fillna(0.0).clip(-50, 50)
    ev["usage"] = ev["usage"].clip(20, 200)  # winsorize: tiny baselines produce wild ratios

    ev["renewed"] = ev["outcome"].isin(KEPT).astype(int)
    ev["expiry_year"] = ev["expiry_date"].dt.year
    ev["half_year"] = ev["expiry_date"].dt.year.astype(str) + np.where(ev["expiry_date"].dt.month <= 6, "-H1", "-H2")
    med = ev.groupby(["submarket", "property_type"])["rent_psf"].transform("median")
    ev["rent_ratio"] = ev["rent_psf"] / med
    ev["lease_share"] = ev["sqft"] / ev["building_sqft"]
    ev["log_building_sqft"] = np.log(ev["building_sqft"])
    ev["log_lease_sqft"] = np.log(ev["sqft"])
    ev["tenant_size"] = pd.cut(ev["lease_share"], [0, 0.1, 0.25, 0.5, 10],
                               labels=["<10% of bldg", "10-25%", "25-50%", "50%+"]).astype(str)
    ev["lead_months"] = lead_months
    excl["usable_events"] = int(len(ev))
    return ev.reset_index(drop=True), excl


def apply_filters(ev: pd.DataFrame, city: str | None = None, property_type: str | None = None,
                  building_class: str | None = None, tenant_industry: str | None = None,
                  submarket: str | None = None, exclude_covid: bool = False,
                  min_lease_share: float | None = None) -> pd.DataFrame:
    out = ev
    for col, val in [("city", city), ("property_type", property_type),
                     ("building_class", building_class), ("tenant_industry", tenant_industry),
                     ("submarket", submarket)]:
        if val:
            vals = [v.strip() for v in str(val).split(",")]
            out = out[out[col].str.lower().isin([v.lower() for v in vals])]
    if min_lease_share:
        out = out[out["lease_share"] >= float(min_lease_share)]
    if exclude_covid:
        out = out[~out["expiry_year"].isin([2020, 2021])]
    return out
