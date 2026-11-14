"""Run: cd backend && pytest -q"""
import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from parallax import analysis
from parallax.agent import ask, parse_filters
from parallax.events import apply_filters, build_lease_events
from parallax.synthetic import generate
from parallax.usage_index import compute_usage


@pytest.fixture(scope="module")
def data():
    d = generate(n_per_city=200, seed=3)
    u = compute_usage(d.buildings, d.captures, d.car_counts)
    ev, excl = build_lease_events(d.buildings, d.leases, u)
    return d, u, ev, excl


def test_peer_normalization_cancels_capture_effect():
    """A capture where every lot is 30% emptier (time of day) must not move the index."""
    b = pd.DataFrame(dict(building_id=[f"b{i}" for i in range(6)], city="X", submarket="S",
                          property_type="office", lat=29.7 + np.arange(6) * 0.001, lon=-95.5,
                          stall_capacity=100, sqft=1e5))
    caps = pd.DataFrame(dict(capture_id=["c1", "c2", "c3"], city="X",
                             capture_date=pd.to_datetime(["2018-03-15", "2019-03-15", "2022-03-15"])))
    cars = []
    for i in range(6):
        for c, f in [("c1", 1.0), ("c2", 1.0), ("c3", 0.7)]:
            cars.append(dict(building_id=f"b{i}", capture_id=c, cars=(50 + 5 * i) * f, quality_flag="ok"))
    u = compute_usage(b, caps, pd.DataFrame(cars))
    assert u[u.capture_id == "c3"]["index"].round(6).eq(100).all()
    assert (u[u.capture_id == "c3"]["abs_index"] < 75).all()  # absolute index keeps the shift


def test_garages_and_bad_captures_excluded(data):
    d, u, ev, excl = data
    assert excl["garage_not_measurable"] > 0
    assert set(ev.parking_type) == {"surface"}
    assert u[u.status.str.startswith("dropped")]["index"].isna().all()


def test_planted_signal_recovered(data):
    _, _, ev, _ = data
    r = analysis.logistic(ev)
    assert r["odds_ratio_per_10pt_drop"] < 1, r


def test_placebo_kills_signal(data):
    _, _, ev, _ = data
    p = analysis.placebo(ev, n_iter=10)
    assert abs(p["placebo_mean_odds_ratio"] - 1) < 0.05


def test_filters():
    assert parse_filters("Only Class A offices in LA?") == {"city": "Los Angeles", "property_type": "office", "building_class": "A"}
    assert parse_filters("houston retail without covid")["exclude_covid"] is True
    assert parse_filters("major tenants")["min_lease_share"] == 0.25


def test_apply_filters(data):
    _, _, ev, _ = data
    s = apply_filters(ev, city="houston", property_type="office")
    assert set(s.city) == {"Houston"} and set(s.property_type) == {"office"}


def test_scripted_agent_streams_events(monkeypatch):
    monkeypatch.setenv("PARALLAX_AGENT", "scripted")

    async def collect():
        return [e async for e in ask("Is the link stronger in Houston or LA?")]
    evs = asyncio.run(collect())
    kinds = {e["type"] for e in evs}
    assert {"plan", "step", "result", "final"} <= kinds
    json.dumps(evs, default=str)


def test_occupancy_link_recovers_synthetic_signal(data):
    from parallax.occupancy import build_panel, link, placebo, tenancies_from_leases
    d, u, _, _ = data
    p = build_panel(d.buildings, u, tenancies_from_leases(d.leases))
    r = link(p)
    assert r["usage_pts_per_10pt_occupancy"] > 0 and r["p_value"] < 0.01
    assert placebo(p, n_iter=5)["passed"]
