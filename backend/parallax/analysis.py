"""Correlation study and validation (plan sections "Correlation study" and
"Validation and robustness"). Every function returns plain dicts so the agent and the
API can pass results straight through as JSON."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.metrics import roc_auc_score

from . import config

warnings.filterwarnings("ignore")

CONTROLS = ["C(city)", "C(property_type)", "C(building_class)", "log_building_sqft",
            "log_lease_sqft", "C(tenant_industry)", "C(expiry_year)", "rent_ratio"]


def _controls_for(ev: pd.DataFrame, drop_year: bool = False) -> list[str]:
    """Drop categorical controls with one level in this slice (e.g. city when filtered to LA)."""
    out = []
    for c in CONTROLS:
        if drop_year and "expiry_year" in c:
            continue
        if c.startswith("C("):
            col = c[2:-1]
            if ev[col].nunique() < 2:
                continue
        out.append(c)
    return out


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def renewal_by_usage_bin(ev: pd.DataFrame, n_bins: int = 5) -> dict:
    """Headline chart: split expiries into usage quintiles, renewal rate in each."""
    if len(ev) < n_bins * 10:
        return {"error": f"only {len(ev)} events - too few to bin", "n": int(len(ev))}
    q = pd.qcut(ev["usage"], n_bins, labels=False, duplicates="drop")
    bins = []
    for b, g in ev.groupby(q):
        k, n = int(g["renewed"].sum()), len(g)
        lo, hi = _wilson(k, n)
        bins.append(dict(bin=int(b) + 1, usage_min=round(float(g["usage"].min()), 1),
                         usage_max=round(float(g["usage"].max()), 1),
                         usage_median=round(float(g["usage"].median()), 1),
                         n=n, renewal_rate=round(k / n, 3), ci_low=round(lo, 3), ci_high=round(hi, 3)))
    lowest, highest = bins[0]["renewal_rate"], bins[-1]["renewal_rate"]
    return dict(n=int(len(ev)), bins=bins,
                emptiest_vs_busiest=dict(emptiest=lowest, busiest=highest,
                                         ratio_nonrenewal=round((1 - lowest) / max(1 - highest, 1e-9), 2)))


def logistic(ev: pd.DataFrame, drop_year: bool = False) -> dict:
    """Logistic regression of renewal on usage + trend + controls.
    Reports the odds ratio of renewing per 10-point DROP in usage."""
    if len(ev) < 80 or ev["renewed"].nunique() < 2:
        return {"error": f"only {len(ev)} events - too few for a regression", "n": int(len(ev))}
    formula = "renewed ~ usage + trend + " + " + ".join(_controls_for(ev, drop_year))
    try:
        m = smf.logit(formula, data=ev).fit(disp=0, maxiter=200)
    except Exception as e:  # perfect separation in tiny slices etc.
        return {"error": f"regression failed: {e}", "n": int(len(ev))}
    b, se = m.params["usage"], m.bse["usage"]
    ci = (b - 1.96 * se, b + 1.96 * se)
    return dict(
        n=int(m.nobs),
        coef_usage=round(float(b), 4), p_value_usage=float(m.pvalues["usage"]),
        odds_ratio_per_10pt_drop=round(float(np.exp(-10 * b)), 3),
        or_ci_low=round(float(np.exp(-10 * ci[1])), 3), or_ci_high=round(float(np.exp(-10 * ci[0])), 3),
        coef_trend=round(float(m.params["trend"]), 4), p_value_trend=float(m.pvalues["trend"]),
        pseudo_r2=round(float(m.prsquared), 4),
        controls=_controls_for(ev, drop_year),
        interpretation=(f"Each 10-point drop in parking usage multiplies the odds of renewal by "
                        f"{np.exp(-10 * b):.2f} (95% CI {np.exp(-10 * ci[1]):.2f}-{np.exp(-10 * ci[0]):.2f}), "
                        f"holding the controls fixed."),
    )


def lead_time_sweep(events_by_lead: dict[int, pd.DataFrame]) -> dict:
    """How far ahead the signal works: refit with usage measured at each lead time."""
    rows = []
    for lead, ev in sorted(events_by_lead.items()):
        r = logistic(ev)
        auc = out_of_sample(ev).get("auc_with_usage")
        rows.append(dict(lead_months=lead, window=f"{lead}-{lead + config.PREDICTOR_WINDOW_MONTHS} months before expiry",
                         n=r.get("n"), odds_ratio_per_10pt_drop=r.get("odds_ratio_per_10pt_drop"),
                         or_ci_low=r.get("or_ci_low"), or_ci_high=r.get("or_ci_high"),
                         p_value=r.get("p_value_usage"), oos_auc=auc))
    valid = [r for r in rows if r["oos_auc"] is not None]
    best = max(valid, key=lambda r: r["oos_auc"]) if valid else None
    return dict(leads=rows, best_lead_months=best["lead_months"] if best else None)


def out_of_sample(ev: pd.DataFrame) -> dict:
    """Fit on 2019-2022 expiries, test on 2023-2026. Compare AUC with and without usage."""
    tr = ev[ev.expiry_year.between(*config.OOS_TRAIN_YEARS)]
    te = ev[ev.expiry_year.between(*config.OOS_TEST_YEARS)]
    if len(tr) < 80 or len(te) < 40 or te.renewed.nunique() < 2:
        return {"error": "too few events for an out-of-sample split", "n_train": len(tr), "n_test": len(te)}
    base_terms = [c for c in ["C(city)", "C(property_type)", "C(building_class)"] if ev[c[2:-1]].nunique() > 1]
    for c in base_terms:  # the test set can't contain categories the model never saw
        col = c[2:-1]
        te = te[te[col].isin(set(tr[col]))]
    base_f = "renewed ~ " + (" + ".join(base_terms) if base_terms else "1")
    full_f = "renewed ~ usage + trend" + ("".join(" + " + t for t in base_terms))
    try:
        mb = smf.logit(base_f, data=tr).fit(disp=0)
        mf = smf.logit(full_f, data=tr).fit(disp=0)
        auc_b = roc_auc_score(te.renewed, mb.predict(te))
        auc_f = roc_auc_score(te.renewed, mf.predict(te))
    except Exception as e:
        return {"error": f"oos fit failed: {e}"}
    return dict(n_train=int(len(tr)), n_test=int(len(te)), auc_baseline=round(float(auc_b), 3),
                auc_with_usage=round(float(auc_f), 3), auc_lift=round(float(auc_f - auc_b), 3))


def placebo(ev: pd.DataFrame, n_iter: int = 30, seed: int = 1) -> dict:
    """Shuffle usage across buildings within the same submarket. The link should vanish."""
    rng = np.random.default_rng(seed)
    real = logistic(ev, drop_year=True)
    ors, sig = [], 0
    for _ in range(n_iter):
        sh = ev.copy()
        sh["usage"] = sh.groupby("submarket")["usage"].transform(lambda s: rng.permutation(s.to_numpy()))
        sh["trend"] = sh.groupby("submarket")["trend"].transform(lambda s: rng.permutation(s.to_numpy()))
        r = logistic(sh, drop_year=True)
        if "error" in r:
            continue
        ors.append(r["odds_ratio_per_10pt_drop"])
        sig += r["p_value_usage"] < 0.05
    return dict(real_odds_ratio=real.get("odds_ratio_per_10pt_drop"),
                placebo_mean_odds_ratio=round(float(np.mean(ors)), 3) if ors else None,
                placebo_share_significant=round(sig / max(len(ors), 1), 3), n_iter=len(ors),
                passed=bool(ors) and abs(np.mean(ors) - 1) < 0.05 and sig / len(ors) <= 0.15)


def covid_check(ev: pd.DataFrame) -> dict:
    with_ = logistic(ev)
    without = logistic(ev[~ev.expiry_year.isin([2020, 2021])])
    return dict(with_covid=_brief(with_), without_2020_2021=_brief(without))


def _brief(r: dict) -> dict:
    return {k: r.get(k) for k in ["n", "odds_ratio_per_10pt_drop", "or_ci_low", "or_ci_high", "p_value_usage", "error"] if r.get(k) is not None}


def subgroups(ev: pd.DataFrame, by: str) -> dict:
    """Where the link holds: refit separately per city / type / class / industry."""
    out = []
    for val, g in ev.groupby(by):
        r = logistic(g, drop_year=len(g) < 400)
        out.append(dict(group=str(val), **_brief(r)))
    return dict(by=by, groups=sorted(out, key=lambda r: r.get("odds_ratio_per_10pt_drop") or 0, reverse=True))


def regional_series(ev: pd.DataFrame, regional_usage: pd.DataFrame, level: str = "city") -> dict:
    """Per city (or submarket) per half-year: average usage index and renewal rate."""
    ru = regional_usage.copy()
    ru["half_year"] = ru["capture_date"].dt.year.astype(str) + np.where(ru["capture_date"].dt.month <= 6, "-H1", "-H2")
    keys = ["city"] if level == "city" else ["city", "submarket"]
    u = ru.groupby(keys + ["half_year"])["usage_index"].mean().reset_index()
    r = ev.groupby(keys + ["half_year"]).agg(renewal_rate=("renewed", "mean"), n_expiries=("renewed", "size")).reset_index()
    m = u.merge(r, on=keys + ["half_year"], how="left").sort_values(keys + ["half_year"])
    m["usage_index"] = m["usage_index"].round(1)
    m["renewal_rate"] = m["renewal_rate"].round(3)
    return dict(level=level, series=m.replace({np.nan: None}).to_dict("records"))


def sample_size(ev: pd.DataFrame, exclusions: dict) -> dict:
    per_city = ev.groupby("city").size().to_dict()
    return dict(exclusions=exclusions, events_per_city=per_city,
                pooled_recommended=any(v < 300 for v in per_city.values()))
