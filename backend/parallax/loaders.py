"""Real-data loaders. Fill these in once the CoStar extract and Vexcel car counts exist.

Each must return DataFrames with exactly the columns the synthetic generator produces,
so nothing downstream changes:

buildings : building_id, name, city, submarket, lat, lon, property_type (office|retail|industrial),
            building_class (A|B|C), sqft, year_built, parking_type (surface|structured), stall_capacity
captures  : capture_id (e.g. "HOU-2020-03"), city, capture_date
car_counts: building_id, capture_id, cars (float|None), quality_flag (ok|cloud|shadow|not_measurable)
leases    : lease_id, building_id, tenant, tenant_industry, sqft, start_date, expiry_date,
            outcome (renewed|expanded|downsized|moved_out), rent_psf
"""
from __future__ import annotations

import pandas as pd

from . import config

REAL_DIR = config.DATA_DIR / "real"


def load_costar() -> tuple[pd.DataFrame, pd.DataFrame]:
    """TODO: map the CoStar extract's columns once we've seen it.
    Expected files: data/real/costar_properties.csv, data/real/costar_leases.csv"""
    props = pd.read_csv(REAL_DIR / "costar_properties.csv")
    leases = pd.read_csv(REAL_DIR / "costar_leases.csv", parse_dates=["start_date", "expiry_date"])
    return props, leases


def load_car_counts() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Output of scripts/batch_car_counts.py (to be written once the probe confirms the
    collections available): data/real/captures.csv and data/real/car_counts.csv"""
    caps = pd.read_csv(REAL_DIR / "captures.csv", parse_dates=["capture_date"])
    cc = pd.read_csv(REAL_DIR / "car_counts.csv")
    return caps, cc


def load_real():
    buildings, leases = load_costar()
    captures, car_counts = load_car_counts()
    return buildings, captures, car_counts, leases
