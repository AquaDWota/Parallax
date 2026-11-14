"""Car counts -> usage index.

Steps (plan section "Car counting and the usage index"):
  1. fill rate      = cars / stall capacity
  2. peer-normalize = fill / median fill of same-type buildings within 2 km, same capture
                      (cancels time of day, weekday and season, which 2 captures a year can't control)
  3. baseline       = express as % of the building's own 2018-2019 average
  4. smooth + flag  = rolling median over 2 captures; a drop is real only if it lasts 2+ captures
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

EARTH_KM = 6371.0


def _pairwise_km(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lon)
    dla = la[:, None] - la[None, :]
    dlo = lo[:, None] - lo[None, :]
    a = np.sin(dla / 2) ** 2 + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin(dlo / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def compute_usage(buildings: pd.DataFrame, captures: pd.DataFrame, car_counts: pd.DataFrame,
                  noise: float = 0.0, seed: int = 0,
                  peer_radius_km: float = config.PEER_RADIUS_KM) -> pd.DataFrame:
    """Return one row per (building, capture) with fill, peer median, index and flags.

    noise: robustness test - multiply every car count by U(1-noise, 1+noise).
    """
    df = car_counts.merge(captures[["capture_id", "capture_date"]], on="capture_id")
    df = df.merge(buildings[["building_id", "city", "submarket", "property_type", "lat", "lon",
                             "stall_capacity", "sqft"]], on="building_id")
    df["cars"] = df["cars"].astype(float)
    if noise:
        rng = np.random.default_rng(seed)
        df["cars"] = df["cars"] * rng.uniform(1 - noise, 1 + noise, len(df))

    usable = df["quality_flag"].eq("ok") & df["cars"].notna()
    df["fill"] = np.where(usable, df["cars"] / df["stall_capacity"], np.nan)

    # --- 2. peer normalization ---
    df["peer_median"] = np.nan
    for (_, _), g in df[usable].groupby(["capture_id", "property_type"]):
        idx = g.index.to_numpy()
        fill = g["fill"].to_numpy()
        d = _pairwise_km(g["lat"].to_numpy(), g["lon"].to_numpy())
        near = (d <= peer_radius_km) & ~np.eye(len(g), dtype=bool)
        sub = g["submarket"].to_numpy()
        med = np.empty(len(g))
        for i in range(len(g)):
            peers = fill[near[i]]
            if len(peers) < 3:  # too few neighbours: fall back to same-type submarket peers
                peers = fill[(sub == sub[i]) & (np.arange(len(g)) != i)]
            med[i] = np.median(peers) if len(peers) else np.nan
        df.loc[idx, "peer_median"] = med
    df["relative"] = df["fill"] / df["peer_median"]

    # --- 3. baseline ---
    y = df["capture_date"].dt.year
    in_base = y.between(*config.BASELINE_YEARS)
    base = df[in_base].groupby("building_id")["relative"].mean().rename("baseline")
    df = df.merge(base, on="building_id", how="left")
    df["index"] = 100 * df["relative"] / df["baseline"]
    # absolute index (no peer normalization): keeps market-wide shifts like COVID,
    # at the cost of capture-to-capture time-of-day noise. Used for regional series only.
    base_fill = df[in_base].groupby("building_id")["fill"].mean().rename("baseline_fill")
    df = df.merge(base_fill, on="building_id", how="left")
    df["abs_index"] = 100 * df["fill"] / df["baseline_fill"]

    # --- 4. smooth and flag ---
    df = df.sort_values(["building_id", "capture_date"]).reset_index(drop=True)
    df["index_smooth"] = (df.groupby("building_id")["index"]
                          .transform(lambda s: s.rolling(2, min_periods=1).median()))
    df["abs_index_smooth"] = (df.groupby("building_id")["abs_index"]
                              .transform(lambda s: s.rolling(2, min_periods=1).median()))
    below = df["index_smooth"] < config.DROP_THRESHOLD
    run = below.groupby((~below).cumsum().astype(str) + df["building_id"]).cumsum()
    df["drop_flag"] = below & (run >= config.DROP_MIN_CAPTURES)

    df["status"] = np.select(
        [df["quality_flag"].eq("not_measurable"), ~usable, df["index"].isna()],
        ["not_measurable", "dropped_" + df["quality_flag"].astype(str), "no_baseline"],
        default="ok")
    return df[["building_id", "capture_id", "capture_date", "city", "submarket", "property_type",
               "sqft", "cars", "fill", "peer_median", "relative", "baseline", "index",
               "index_smooth", "abs_index", "abs_index_smooth", "drop_flag", "status", "quality_flag"]]


def regional_index(usage: pd.DataFrame, level: str = "submarket") -> pd.DataFrame:
    """Sq-ft-weighted average ABSOLUTE usage index (% of 2018-19 fill) per city or submarket
    per capture. Absolute, not peer-relative: peer-relative averages to ~100 by construction."""
    keys = ["city"] if level == "city" else ["city", "submarket"]
    u = usage[usage["abs_index"].notna()]
    u = u.assign(abs_index=u["abs_index"].clip(0, 300))
    g = u.assign(w=u["sqft"] * u["abs_index"]).groupby(keys + ["capture_id", "capture_date"])
    out = (g["w"].sum() / g["sqft"].sum()).rename("usage_index").reset_index()
    out["n_buildings"] = g.size().to_numpy()
    return out.sort_values(keys + ["capture_date"])


def quality_log(usage: pd.DataFrame) -> dict:
    """What was dropped and why - judges will ask."""
    return usage["status"].value_counts().to_dict()
