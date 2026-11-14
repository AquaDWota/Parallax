"""Building occupancy over time, and how parking usage relates to it.

Occupancy at date d = sq ft of tenancies active on d / building size (RBA), in %.
  real:      every CoStar tenancy (costar_occupancy.csv), not just the ones with lease deals
  synthetic: the generated leases

The study (plan fallback, now the headline):
  1. link        - within a building, does lot usage move with occupancy? (building + period fixed effects)
  2. lead / lag  - is usage aligned with occupancy before, at, or after the capture?
  3. drop        - after a sharp drop in usage (> 30 points between captures), what happens to occupancy next?
  4. placebo     - shuffle usage across buildings within a period: the link should vanish
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

warnings.filterwarnings("ignore")

OFFSETS = (-24, -12, 0, 12, 24)
DATA_END = pd.Timestamp("2026-11-01")
BIG_DROP = -30.0


def tenancies_from_leases(leases: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(dict(building_id=leases.building_id, from_date=leases.start_date,
                             to_date=leases.expiry_date, sqft=leases.sqft))


def occupancy_at(ten: pd.DataFrame, building_sqft: pd.Series, when: pd.DataFrame) -> np.ndarray:
    """when: building_id, date -> occupancy % (capped at 120)."""
    by_b = {k: (g.from_date.to_numpy(), g.to_date.to_numpy(), g.sqft.to_numpy()) for k, g in ten.groupby("building_id")}
    out = np.full(len(when), np.nan)
    for i, (bid, d) in enumerate(zip(when.building_id, when.date)):
        t = by_b.get(bid)
        size = building_sqft.get(bid)
        if t is None or not size or pd.isna(d):
            continue
        d = np.datetime64(d)
        f, to, sq = t
        active = (f <= d) & (pd.isna(to) | (to >= d))
        out[i] = min(sq[active].sum() / size, 1.2) * 100
    return out


def build_panel(buildings: pd.DataFrame, usage: pd.DataFrame, tenancies: pd.DataFrame) -> pd.DataFrame:
    """One row per (building, capture) with a usage index, plus occupancy at each offset."""
    has_ten = set(tenancies.building_id)
    u = usage[usage["index"].notna() & usage.building_id.isin(has_ten)].copy()
    extra = [c for c in ["property_type", "building_class", "name", "parking_detail"]
             if c in buildings.columns and c not in u.columns]
    u = u.merge(buildings[["building_id"] + extra], on="building_id", how="left")
    size = buildings.set_index("building_id")["sqft"]
    for k in OFFSETS:
        when = pd.DataFrame(dict(building_id=u.building_id, date=u.capture_date + pd.DateOffset(months=k)))
        occ = occupancy_at(tenancies, size, when)
        if k > 0:
            occ[(u.capture_date + pd.DateOffset(months=k) > DATA_END).to_numpy()] = np.nan
        u[f"occ_{k}" if k >= 0 else f"occ_m{-k}"] = occ
    u["usage"] = u["index"].clip(0, 250)
    u["period"] = u["capture_date"].dt.year.astype(str)
    u = u.sort_values(["building_id", "capture_date"])
    u["d_usage"] = u.groupby("building_id")["usage"].diff()
    u["d_occ"] = u.groupby("building_id")["occ_0"].diff()
    u["d_occ_next"] = u.groupby("building_id")["occ_0"].shift(-1) - u["occ_0"]
    return u.reset_index(drop=True)


def apply_filters(p: pd.DataFrame, city=None, property_type=None, building_class=None, **_) -> pd.DataFrame:
    for col, val in [("city", city), ("property_type", property_type), ("building_class", building_class)]:
        if val:
            vals = [v.strip().lower() for v in str(val).split(",")]
            p = p[p[col].astype(str).str.lower().isin(vals)]
    return p


def _fe(p: pd.DataFrame, y: str, x: str):
    d = p.dropna(subset=[y, x])
    if d.building_id.nunique() < 8 or len(d) < 40:
        return None, d
    f = f"{y} ~ Q('{x}') + C(building_id) + C(period)"
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d.building_id})
    return m, d


def link(p: pd.DataFrame) -> dict:
    """Within-building: usage index vs occupancy at the same capture."""
    m, d = _fe(p, "usage", "occ_0")
    if m is None:
        return {"error": f"too few buildings ({d.building_id.nunique()}) for the within-building test", "n": int(len(d))}
    b, se = m.params["Q('occ_0')"], m.bse["Q('occ_0')"]
    # chart: occupancy vs the building's own average, against usage vs its own average
    dd = d.assign(occ_dev=d.occ_0 - d.groupby("building_id").occ_0.transform("mean"),
                  use_dev=d.usage - d.groupby("building_id").usage.transform("mean"))
    dd = dd[dd.groupby("building_id").occ_0.transform("std") > 0.5]
    bins = []
    if len(dd) >= 50:
        edges = [-1e9, -15, -5, 5, 15, 1e9]
        labels = ["15+ pts below", "5-15 below", "within 5", "5-15 above", "15+ above"]
        cut = pd.cut(dd.occ_dev, edges, labels=labels)
        for lab, g in dd.groupby(cut, observed=False):
            if len(g) < 5:
                continue
            se_g = g.use_dev.std(ddof=1) / np.sqrt(len(g))
            bins.append(dict(label=str(lab), n=int(len(g)), occ_dev=round(float(g.occ_dev.mean()), 1),
                             usage_dev=round(float(g.use_dev.mean()), 1),
                             ci_low=round(float(g.use_dev.mean() - 1.96 * se_g), 1),
                             ci_high=round(float(g.use_dev.mean() + 1.96 * se_g), 1)))
    return dict(n=int(m.nobs), n_buildings=int(d.building_id.nunique()),
                usage_pts_per_10pt_occupancy=round(float(10 * b), 2),
                ci_low=round(float(10 * (b - 1.96 * se)), 2), ci_high=round(float(10 * (b + 1.96 * se)), 2),
                p_value=float(m.pvalues["Q('occ_0')"]), bins=bins,
                interpretation=(f"Within the same building, each 10 points of occupancy comes with {10 * b:+.1f} points "
                                f"of parking usage (95% CI {10 * (b - 1.96 * se):+.1f} to {10 * (b + 1.96 * se):+.1f}), "
                                f"across {d.building_id.nunique()} buildings."))


def lead_lag(p: pd.DataFrame) -> dict:
    """Usage at the capture vs occupancy 24/12 months before, at, and 12/24 months after."""
    rows = []
    for k in OFFSETS:
        col = f"occ_{k}" if k >= 0 else f"occ_m{-k}"
        m, d = _fe(p, "usage", col)
        if m is None:
            rows.append(dict(offset_months=k, n=int(len(d)), error="too few"))
            continue
        b, se = m.params[f"Q('{col}')"], m.bse[f"Q('{col}')"]
        rows.append(dict(offset_months=k, n=int(m.nobs), coef_per_10pt=round(float(10 * b), 2),
                         ci_low=round(float(10 * (b - 1.96 * se)), 2), ci_high=round(float(10 * (b + 1.96 * se)), 2),
                         p_value=float(m.pvalues[f"Q('{col}')"])))
    return dict(offsets=rows)


def drop_followthrough(p: pd.DataFrame, threshold: float = BIG_DROP) -> dict:
    """After usage falls more than `threshold` points between captures, how does occupancy change next?"""
    d = p.dropna(subset=["d_usage", "d_occ_next"])
    if len(d) < 30:
        return {"error": "too few consecutive capture pairs", "n": int(len(d))}
    drop = d[d.d_usage < threshold].d_occ_next
    rest = d[d.d_usage >= threshold].d_occ_next
    if len(drop) < 5:
        return {"error": f"only {len(drop)} sharp drops", "n": int(len(d))}
    t = stats.ttest_ind(drop, rest, equal_var=False)
    fall_drop = float((drop < -5).mean())
    fall_rest = float((rest < -5).mean())
    return dict(threshold=threshold, n_drops=int(len(drop)), n_rest=int(len(rest)),
                occ_change_after_drop=round(float(drop.mean()), 2), occ_change_otherwise=round(float(rest.mean()), 2),
                difference=round(float(drop.mean() - rest.mean()), 2), p_value=float(t.pvalue),
                share_losing_5pts_after_drop=round(fall_drop, 3), share_losing_5pts_otherwise=round(fall_rest, 3),
                interpretation=(f"After a lot emptied by more than {-threshold:.0f} points, building occupancy changed "
                                f"{drop.mean():+.1f} points by the next capture, against {rest.mean():+.1f} otherwise "
                                f"({len(drop)} drops)."))


def placebo(p: pd.DataFrame, n_iter: int = 30, seed: int = 2) -> dict:
    rng = np.random.default_rng(seed)
    coefs = []
    for _ in range(n_iter):
        sh = p.copy()
        sh["usage"] = sh.groupby("period")["usage"].transform(lambda s: rng.permutation(s.to_numpy()))
        m, _ = _fe(sh, "usage", "occ_0")
        if m is not None:
            coefs.append(10 * m.params["Q('occ_0')"])
    real = link(p)
    return dict(real=real.get("usage_pts_per_10pt_occupancy"),
                placebo_mean=round(float(np.mean(coefs)), 2) if coefs else None,
                placebo_p95=round(float(np.percentile(np.abs(coefs), 95)), 2) if coefs else None,
                passed=bool(coefs) and real.get("usage_pts_per_10pt_occupancy") is not None
                and abs(real["usage_pts_per_10pt_occupancy"]) > np.percentile(np.abs(coefs), 95))


def by_group(p: pd.DataFrame, by: str) -> dict:
    out = []
    for val, g in p.groupby(by):
        r = link(g)
        out.append(dict(group=str(val), n=r.get("n"), n_buildings=r.get("n_buildings"),
                        usage_pts_per_10pt_occupancy=r.get("usage_pts_per_10pt_occupancy"),
                        p_value=r.get("p_value"), error=r.get("error")))
    return dict(by=by, groups=sorted(out, key=lambda r: -(r["usage_pts_per_10pt_occupancy"] or -99)))
