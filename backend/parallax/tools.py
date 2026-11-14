"""Analysis tools the agents call. Each takes optional slice filters and returns a JSON
string (what LLM tools need) built from a plain dict (what the UI charts need).

Filters (all optional, comma-separated values allowed):
  city: "Houston" | "Los Angeles"
  property_type: "office" | "retail" | "industrial"
  building_class: "A" | "B" | "C"
  tenant_industry: tech, finance, legal, healthcare, energy, retail, logistics, government, other
  submarket: e.g. "Energy Corridor"
  exclude_covid: drop expiries in 2020-2021
  min_lease_share: e.g. 0.25 = only tenants leasing 25%+ of their building
"""
from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd

from . import analysis
from .events import apply_filters
from .store import get_store, run_sql as _run_sql


def _json(d: dict) -> str:
    return json.dumps(d, default=lambda o: o.item() if isinstance(o, np.generic) else str(o))


def _slice(city=None, property_type=None, building_class=None, tenant_industry=None,
           submarket=None, exclude_covid=False, min_lease_share=None, lead_months=0):
    ev, excl = get_store().events(int(lead_months or 0))
    f = dict(city=city, property_type=property_type, building_class=building_class,
             tenant_industry=tenant_industry, submarket=submarket,
             exclude_covid=bool(exclude_covid), min_lease_share=min_lease_share)
    return apply_filters(ev, **f), excl, {k: v for k, v in f.items() if v}


# ---------------------------------------------------------------- lease-event builder
def build_lease_events(city: Optional[str] = None, property_type: Optional[str] = None,
                       building_class: Optional[str] = None, tenant_industry: Optional[str] = None,
                       submarket: Optional[str] = None, exclude_covid: bool = False,
                       min_lease_share: Optional[float] = None) -> str:
    """Build the lease-expiry table for a slice: every expiry 2019-2026 with its outcome,
    the building's parking usage in the 12 months before, and controls. Reports what was
    excluded and why (garage buildings can't be measured from above)."""
    ev, excl, f = _slice(city, property_type, building_class, tenant_industry, submarket,
                         exclude_covid, min_lease_share)
    return _json(dict(
        filters=f, n_events=int(len(ev)), exclusions_all_data=excl,
        renewal_rate=round(float(ev.renewed.mean()), 3) if len(ev) else None,
        outcome_mix=ev.outcome.value_counts().to_dict(),
        events_per_city=ev.groupby("city").size().to_dict(),
        events_per_type=ev.groupby("property_type").size().to_dict(),
        warning=("fewer than 300 events in a city - pool cities" if any(v < 300 for v in ev.groupby("city").size()) else None),
    ))


# ---------------------------------------------------------------- statistician
def usage_vs_renewal(city: Optional[str] = None, property_type: Optional[str] = None,
                     building_class: Optional[str] = None, tenant_industry: Optional[str] = None,
                     submarket: Optional[str] = None, exclude_covid: bool = False,
                     min_lease_share: Optional[float] = None) -> str:
    """Headline chart: split lease expiries into 5 usage bins and return the renewal rate
    (with 95% CI) in each. Usage = parking vs. neighbours, as % of the building's 2018-19 level."""
    ev, _, f = _slice(city, property_type, building_class, tenant_industry, submarket, exclude_covid, min_lease_share)
    return _json(dict(filters=f, **analysis.renewal_by_usage_bin(ev)))


def regression(city: Optional[str] = None, property_type: Optional[str] = None,
               building_class: Optional[str] = None, tenant_industry: Optional[str] = None,
               submarket: Optional[str] = None, exclude_covid: bool = False,
               min_lease_share: Optional[float] = None) -> str:
    """Logistic regression of renewal (kept all its space: yes/no) on usage and usage trend,
    controlling for city, type, class, size, lease size, industry, expiry year and rent vs.
    submarket. Returns the odds ratio of renewal per 10-point drop in usage, with 95% CI."""
    ev, _, f = _slice(city, property_type, building_class, tenant_industry, submarket, exclude_covid, min_lease_share)
    return _json(dict(filters=f, **analysis.logistic(ev)))


def lead_time(city: Optional[str] = None, property_type: Optional[str] = None,
              building_class: Optional[str] = None, tenant_industry: Optional[str] = None,
              submarket: Optional[str] = None, exclude_covid: bool = False,
              min_lease_share: Optional[float] = None) -> str:
    """Repeat the regression with usage measured in windows ending 0, 6/12, ... months before
    expiry. The window with the best out-of-sample AUC says how far ahead the signal works."""
    by_lead = {}
    f = {}
    from . import config
    for L in config.LEAD_TIMES_MONTHS:
        ev, _, f = _slice(city, property_type, building_class, tenant_industry, submarket,
                          exclude_covid, min_lease_share, lead_months=L)
        by_lead[L] = ev
    return _json(dict(filters=f, **analysis.lead_time_sweep(by_lead)))


def validate(city: Optional[str] = None, property_type: Optional[str] = None,
             building_class: Optional[str] = None, tenant_industry: Optional[str] = None,
             submarket: Optional[str] = None, min_lease_share: Optional[float] = None,
             include_noise_test: bool = True) -> str:
    """Robustness tests designed to break the result: out-of-sample AUC (fit 2019-22, test
    2023-26) vs. a city/type/class baseline; placebo (shuffle usage within submarket - link
    should vanish); with vs. without 2020-21; +/-15% car-count noise; sample size."""
    ev, excl, f = _slice(city, property_type, building_class, tenant_industry, submarket, False, min_lease_share)
    out = dict(filters=f,
               out_of_sample=analysis.out_of_sample(ev),
               placebo=analysis.placebo(ev, n_iter=20),
               covid=analysis.covid_check(ev),
               sample_size=analysis.sample_size(ev, excl))
    if include_noise_test:
        noisy = apply_filters(get_store().events_with_noise(0.15), **{k: v for k, v in f.items()})
        out["detector_noise_15pct"] = analysis._brief(analysis.logistic(noisy))
    return _json(out)


def compare_groups(by: str = "city", city: Optional[str] = None, property_type: Optional[str] = None,
                   building_class: Optional[str] = None, exclude_covid: bool = False,
                   min_lease_share: Optional[float] = None) -> str:
    """Where the link holds: rerun the regression separately for each value of `by`
    (one of: city, property_type, building_class, tenant_industry, submarket, tenant_size)."""
    if by not in {"city", "property_type", "building_class", "tenant_industry", "submarket", "tenant_size"}:
        return _json({"error": f"can't group by {by}"})
    ev, _, f = _slice(city, property_type, building_class, None, None, exclude_covid, min_lease_share)
    return _json(dict(filters=f, **analysis.subgroups(ev, by)))


def run_sql(query: str) -> str:
    """Read-only SQL (DuckDB) over tables: buildings, captures, car_counts, leases, usage.
    usage has building_id, capture_id, capture_date, index_smooth (peer-relative, % of 2018-19),
    abs_index_smooth, status. Max 200 rows returned."""
    try:
        df = _run_sql(query)
    except Exception as e:
        return _json({"error": str(e)})
    return _json({"rows": df.astype(object).where(df.notna(), None).to_dict("records"), "n": len(df)})


# ---------------------------------------------------------------- imagery analyst
def regional_series(level: str = "city", city: Optional[str] = None) -> str:
    """Per half-year 2018-2026: average parking usage (sq-ft weighted, % of 2018-19 fill)
    and lease renewal rate, by city (level='city') or CoStar submarket (level='submarket')."""
    s = get_store()
    ev, _ = s.events(0)
    ru = s.regional_city if level == "city" else s.regional_submarket
    if city:
        ru = ru[ru.city.str.lower() == city.lower()]
        ev = ev[ev.city.str.lower() == city.lower()]
    return _json(analysis.regional_series(ev, ru, level))


def imagery_quality(city: Optional[str] = None) -> str:
    """What the imagery pipeline dropped and why: garage buildings (not measurable), cloud,
    shadow, buildings without a 2018-19 baseline."""
    u = get_store().usage
    if city:
        u = u[u.city.str.lower() == city.lower()]
    per_capture = (u[u.status.str.startswith("dropped")].groupby(["capture_id", "status"]).size()
                   .reset_index(name="n").to_dict("records"))
    return _json(dict(status_counts=u.status.value_counts().to_dict(),
                      buildings_not_measurable=int(u[u.status == "not_measurable"].building_id.nunique()),
                      dropped_by_capture=per_capture[:40]))


def example_buildings(which: str = "emptiest", n: int = 3, city: Optional[str] = None,
                      property_type: Optional[str] = None, building_class: Optional[str] = None,
                      min_lease_share: Optional[float] = 0.25, usage_bin: Optional[int] = None) -> str:
    """Example lease expiries for the demo: which='emptiest' (lowest usage before expiry) or
    'busiest'; or usage_bin=1..5 for expiries in that usage quintile. Returns building, tenant,
    outcome, usage before expiry and the usage history."""
    ev, _, f = _slice(city, property_type, building_class, None, None, False, min_lease_share)
    if usage_bin:
        q = pd.qcut(ev["usage"], 5, labels=False, duplicates="drop") + 1
        ev = ev[q == int(usage_bin)].sample(frac=1, random_state=int(usage_bin))
        # show a mix: a tenant that left and one that stayed when possible
        ev = pd.concat([ev[ev.renewed == 0].head(2), ev[ev.renewed == 1].head(2)]).sample(frac=1, random_state=0)
    else:
        ev = ev.sort_values("usage", ascending=(which != "busiest"))
    pick = ev.head(max(int(n) * 4, 12)).drop_duplicates("building_id").head(int(n))
    u = get_store().usage
    out = []
    for r in pick.itertuples():
        hist = u[u.building_id == r.building_id].sort_values("capture_date")
        out.append(dict(
            building_id=r.building_id, name=r.name, city=r.city, submarket=r.submarket,
            property_type=r.property_type, building_class=r.building_class, lat=r.lat, lon=r.lon,
            tenant=r.tenant, tenant_industry=r.tenant_industry, lease_sqft=int(r.sqft),
            lease_share=round(float(r.lease_share), 2), expiry=str(r.expiry_date.date()),
            outcome=r.outcome, usage_before_expiry=round(float(r.usage), 1),
            history=[dict(capture_id=h.capture_id, date=str(h.capture_date.date()),
                          index=None if pd.isna(h.index_smooth) else round(float(h.index_smooth), 1),
                          cars=None if pd.isna(h.cars) else int(h.cars), status=h.status)
                     for h in hist.itertuples()],
        ))
    return _json(dict(filters=f, which=which, usage_bin=usage_bin, examples=out))


# ---------------------------------------------------------------- market analyst
def submarket_context(city: Optional[str] = None) -> str:
    """CoStar submarket context: buildings, measurable share, latest usage index, renewal
    rate since 2023 and median rent per submarket."""
    s = get_store()
    ev, _ = s.events(0)
    b = s.buildings
    rs = s.regional_submarket
    latest = rs.sort_values("capture_date").groupby(["city", "submarket"]).tail(1)
    if city:
        b, ev, latest = (d[d.city.str.lower() == city.lower()] for d in (b, ev, latest))
    agg = b.groupby(["city", "submarket"]).agg(buildings=("building_id", "size"),
                                               surface_share=("parking_type", lambda x: round(float((x == "surface").mean()), 2)))
    recent = ev[ev.expiry_year >= 2023].groupby(["city", "submarket"]).agg(
        renewal_rate_2023_on=("renewed", "mean"), median_rent_psf=("rent_psf", "median"))
    m = agg.join(recent).join(latest.set_index(["city", "submarket"])["usage_index"].rename("latest_usage_index")).reset_index()
    return _json(dict(submarkets=m.round(3).replace({np.nan: None}).to_dict("records")))


ALL_TOOLS = [build_lease_events, usage_vs_renewal, regression, lead_time, validate, compare_groups,
             run_sql, regional_series, imagery_quality, example_buildings, submarket_context]
TOOLS_BY_NAME = {t.__name__: t for t in ALL_TOOLS}
