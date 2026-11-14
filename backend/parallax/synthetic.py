"""Synthetic Houston + LA dataset with the same shape as the real CoStar + Vexcel data.

Used so the whole pipeline, agent and UI run end to end before real data arrives.
Swap in the real loaders (parallax.loaders) and nothing downstream changes.

The generator plants a known signal: tenants who downsize or move out reduce how much
they use the building 6-24 months before their lease expires. If the analysis can't
recover it, the analysis is broken.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SUBMARKETS = {
    "Houston": {
        "Energy Corridor": (29.781, -95.633),
        "Westchase": (29.727, -95.560),
        "Galleria": (29.739, -95.462),
        "Greenway Plaza": (29.731, -95.432),
        "North Belt": (29.943, -95.410),
        "The Woodlands": (30.166, -95.466),
        "Katy Freeway West": (29.786, -95.704),
        "Sugar Land": (29.598, -95.622),
    },
    "Los Angeles": {
        "Burbank": (34.181, -118.309),
        "Pasadena": (34.147, -118.132),
        "Torrance": (33.836, -118.341),
        "El Segundo": (33.919, -118.400),
        "Woodland Hills": (34.168, -118.605),
        "Commerce": (34.000, -118.159),
        "Long Beach": (33.804, -118.167),
        "City of Industry": (34.020, -117.958),
    },
}
CITY_CODE = {"Houston": "HOU", "Los Angeles": "LA"}
INDUSTRIES = ["tech", "finance", "legal", "healthcare", "energy", "retail",
              "logistics", "government", "other"]
_NAME_A = ["Summit", "Pacific", "Lone Star", "Harbor", "Meridian", "Apex", "Cypress",
           "Golden", "Bayou", "Sierra", "Redwood", "Gulf", "Orion", "Keystone", "Vista"]
_NAME_B = ["Holdings", "Partners", "Systems", "Group", "Logistics", "Health", "Energy",
           "Capital", "Labs", "Services", "Retail", "Legal", "Analytics", "Supply"]


def capture_dates() -> list[pd.Timestamp]:
    """Two captures a year, Mar and Sep, 2018-03 to 2026-03 (17 captures)."""
    out = []
    for y in range(2018, 2027):
        out.append(pd.Timestamp(y, 3, 15))
        if y < 2026:
            out.append(pd.Timestamp(y, 9, 15))
    return out


@dataclass
class SyntheticData:
    buildings: pd.DataFrame
    captures: pd.DataFrame
    car_counts: pd.DataFrame
    leases: pd.DataFrame


def _months(a: pd.Timestamp, b: pd.Timestamp) -> float:
    return (b - a).days / 30.44


def generate(n_per_city: int = 600, seed: int = 7) -> SyntheticData:
    rng = np.random.default_rng(seed)

    # ---------------- buildings ----------------
    rows = []
    bid = 0
    for city, subs in SUBMARKETS.items():
        names = list(subs)
        for _ in range(n_per_city):
            sub = names[rng.integers(len(names))]
            clat, clon = subs[sub]
            ptype = rng.choice(["office", "retail", "industrial"], p=[0.5, 0.25, 0.25])
            bclass = rng.choice(["A", "B", "C"], p=[0.3, 0.45, 0.25])
            sqft = float(np.round(rng.lognormal(
                {"office": 11.3, "retail": 10.6, "industrial": 11.6}[ptype], 0.55), -2))
            p_surface = 0.45 if (ptype == "office" and bclass == "A") else 0.85
            parking = "surface" if rng.random() < p_surface else "structured"
            ratio = {"office": 3.5, "retail": 4.5, "industrial": 1.2}[ptype]
            cap = int(max(20, sqft / 1000 * ratio * rng.uniform(0.8, 1.2)))
            rows.append(dict(
                building_id=f"B{bid:05d}",
                name=f"{rng.integers(100, 9999)} {rng.choice(_NAME_A)} {rng.choice(['Pkwy', 'Blvd', 'Dr', 'Way', 'Ave'])}",
                city=city, submarket=sub,
                lat=clat + rng.normal(0, 0.012), lon=clon + rng.normal(0, 0.014),
                property_type=ptype, building_class=bclass, sqft=sqft,
                year_built=int(rng.integers(1972, 2019)), parking_type=parking,
                stall_capacity=cap,
            ))
            bid += 1
    buildings = pd.DataFrame(rows)

    # ---------------- captures ----------------
    cap_rows = []
    for city, code in CITY_CODE.items():
        for d in capture_dates():
            d2 = d + pd.Timedelta(days=int(rng.integers(-10, 11)))
            cap_rows.append(dict(
                capture_id=f"{code}-{d.year}-{d.month:02d}", city=city,
                capture_date=d2,
                # time of day / weekday / season effect shared by every lot in the capture;
                # peer normalization is what cancels this out
                tod_factor=rng.uniform(0.78, 1.15),
            ))
    captures = pd.DataFrame(cap_rows)

    # ---------------- leases ----------------
    sim_start, sim_end = pd.Timestamp(2015, 1, 1), pd.Timestamp(2026, 10, 1)
    sub_rent = {s: rng.uniform(18, 42) for c in SUBMARKETS.values() for s in c}
    lease_rows = []
    tenant_seq = 0

    def new_tenant(ptype: str) -> tuple[str, str]:
        nonlocal tenant_seq
        tenant_seq += 1
        p = {"office": [.2, .15, .1, .12, .12, .02, .02, .07, .2],
             "retail": [.02, .05, .02, .1, .01, .6, .05, .02, .13],
             "industrial": [.05, .01, .01, .05, .12, .06, .55, .03, .12]}[ptype]
        ind = rng.choice(INDUSTRIES, p=p)
        return f"{rng.choice(_NAME_A)} {rng.choice(_NAME_B)} #{tenant_seq}", ind

    lid = 0
    for b in buildings.itertuples():
        n_suites = int(rng.integers(1, 7))
        shares = rng.dirichlet(np.full(n_suites, 0.6)) * rng.uniform(0.8, 0.97)
        for share in shares:
            suite_sqft = max(1500.0, round(b.sqft * share, -2))
            tenant, ind = new_tenant(b.property_type)
            start = sim_start - pd.Timedelta(days=int(rng.integers(0, 365 * 5)))
            sqft_now = suite_sqft
            while start < sim_end:
                term_y = int(rng.choice([3, 5, 7], p=[.35, .45, .2]))
                expiry = start + pd.DateOffset(years=term_y)
                rent = sub_rent[b.submarket] * {"A": 1.3, "B": 1.0, "C": .75}[b.building_class]
                rent *= {"office": 1.0, "retail": 1.1, "industrial": .45}[b.property_type]
                rent *= rng.lognormal(0, 0.12)
                # outcome model (the controls matter, usage is planted via activity below)
                logit = 0.9
                logit += {"A": .35, "B": 0, "C": -.35}[b.building_class]
                if b.property_type == "office" and 2020 <= expiry.year <= 2022:
                    logit -= 0.8
                if ind == "tech":
                    logit -= 0.35
                rent_ratio = rent / (sub_rent[b.submarket] * {"office": 1.0, "retail": 1.1, "industrial": .45}[b.property_type])
                logit -= 1.2 * (rent_ratio - 1.0)
                logit += rng.normal(0, 0.9)  # unobserved tenant reasons
                p_keep = 1 / (1 + np.exp(-logit))
                u = rng.random()
                if u < p_keep * 0.88:
                    outcome = "renewed"
                elif u < p_keep:
                    outcome = "expanded"
                elif u < p_keep + (1 - p_keep) * 0.35:
                    outcome = "downsized"
                else:
                    outcome = "moved_out"
                lease_rows.append(dict(
                    lease_id=f"L{lid:06d}", building_id=b.building_id, tenant=tenant,
                    tenant_industry=ind, sqft=sqft_now, start_date=start,
                    expiry_date=expiry, outcome=outcome, rent_psf=round(rent, 2),
                    # hidden: when this tenant started winding down (months before expiry)
                    wind_down_m=float(rng.uniform(6, 24)) if outcome in ("moved_out", "downsized") else 0.0,
                    remote_share=float(rng.uniform(0.25, 0.75)) if b.property_type == "office" else float(rng.uniform(0.0, 0.25)),
                ))
                lid += 1
                if outcome == "moved_out":
                    gap = int(rng.integers(4, 19))
                    start = expiry + pd.DateOffset(months=gap)
                    tenant, ind = new_tenant(b.property_type)
                    sqft_now = suite_sqft
                else:
                    start = expiry
                    if outcome == "downsized":
                        sqft_now = round(sqft_now * 0.6, -2)
                    elif outcome == "expanded":
                        sqft_now = round(min(suite_sqft * 1.3, sqft_now * 1.2), -2)
    leases = pd.DataFrame(lease_rows)

    # ---------------- car counts ----------------
    covid = pd.Timestamp(2020, 3, 15)
    base_fill = {"office": 0.72, "retail": 0.55, "industrial": 0.6}
    lease_by_b = {k: g for k, g in leases.groupby("building_id")}
    cc_rows = []
    for b in buildings.itertuples():
        bl = lease_by_b.get(b.building_id)
        recov = rng.uniform(0.4, 1.0)  # building-specific post-COVID recovery speed
        for c in captures[captures.city == b.city].itertuples():
            t = c.capture_date
            active = bl[(bl.start_date <= t) & (bl.expiry_date > t)] if bl is not None else bl
            occ = 0.0
            if active is not None and len(active):
                for l in active.itertuples():
                    act = 1.0
                    if t >= covid:
                        m = _months(covid, t)
                        depth = l.remote_share
                        act *= 1 - depth * np.exp(-m * recov / 18) - depth * 0.35 * (1 - np.exp(-m * recov / 18))
                    if l.wind_down_m > 0:
                        m_left = _months(t, l.expiry_date)
                        if m_left < l.wind_down_m:
                            floor = 0.35 if l.outcome == "moved_out" else 0.65
                            act *= 1 - (1 - floor) * (1 - m_left / l.wind_down_m)
                    occ += l.sqft * max(act, 0.05)
            occ = min(occ / b.sqft, 1.2)
            expected = b.stall_capacity * (0.05 + base_fill[b.property_type] * occ) * c.tod_factor
            cars = int(rng.poisson(max(expected * rng.lognormal(0, 0.10), 0.1)))
            cars = min(cars, b.stall_capacity)
            r = rng.random()
            flag = "cloud" if r < 0.04 else ("shadow" if r < 0.06 else "ok")
            cc_rows.append(dict(building_id=b.building_id, capture_id=c.capture_id,
                                cars=cars if b.parking_type == "surface" else None,
                                quality_flag=flag if b.parking_type == "surface" else "not_measurable"))
    car_counts = pd.DataFrame(cc_rows)

    leases = leases.drop(columns=["wind_down_m", "remote_share"])
    captures = captures.drop(columns=["tod_factor"])
    return SyntheticData(buildings, captures, car_counts, leases)
