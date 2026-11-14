"""Builds the precomputed tables once (the 'batch job') and keeps them in DuckDB.

    python -m scripts.build            # synthetic data
    PARALLAX_DATA_MODE=real python -m scripts.build   # real CoStar + Vexcel (see loaders.py)

The API and agent tools read from the in-memory cache returned by `get_store()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import duckdb
import pandas as pd

from . import config
from .events import build_lease_events
from .usage_index import compute_usage, regional_index

TABLES = ["buildings", "captures", "car_counts", "leases", "usage"]


@dataclass
class Store:
    buildings: pd.DataFrame
    captures: pd.DataFrame
    car_counts: pd.DataFrame
    leases: pd.DataFrame
    usage: pd.DataFrame
    _events: dict = field(default_factory=dict)

    @property
    def regional_city(self) -> pd.DataFrame:
        if "rc" not in self._events:
            self._events["rc"] = regional_index(self.usage, "city")
        return self._events["rc"]

    @property
    def regional_submarket(self) -> pd.DataFrame:
        if "rs" not in self._events:
            self._events["rs"] = regional_index(self.usage, "submarket")
        return self._events["rs"]

    def events(self, lead_months: int = 0) -> tuple[pd.DataFrame, dict]:
        key = ("ev", lead_months)
        if key not in self._events:
            self._events[key] = build_lease_events(self.buildings, self.leases, self.usage, lead_months)
        return self._events[key]

    def events_with_noise(self, noise: float = 0.15, seed: int = 0) -> pd.DataFrame:
        u = compute_usage(self.buildings, self.captures, self.car_counts, noise=noise, seed=seed)
        return build_lease_events(self.buildings, self.leases, u)[0]


def build(mode: str = config.DATA_MODE) -> Store:
    if mode == "synthetic":
        from .synthetic import generate
        d = generate()
        buildings, captures, car_counts, leases = d.buildings, d.captures, d.car_counts, d.leases
    else:
        from .loaders import load_real
        buildings, captures, car_counts, leases = load_real()
    usage = compute_usage(buildings, captures, car_counts)
    con = duckdb.connect(str(config.DB_PATH))
    for name, df in dict(buildings=buildings, captures=captures, car_counts=car_counts,
                         leases=leases, usage=usage).items():
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()
    get_store.cache_clear()
    return Store(buildings, captures, car_counts, leases, usage)


@lru_cache(maxsize=1)
def get_store() -> Store:
    if not config.DB_PATH.exists():
        return build()
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        dfs = {t: con.execute(f"SELECT * FROM {t}").df() for t in TABLES}
    except duckdb.CatalogException:
        con.close()
        return build()
    con.close()
    for t in ["captures", "usage"]:
        dfs[t]["capture_date"] = pd.to_datetime(dfs[t]["capture_date"])
    for c in ["start_date", "expiry_date"]:
        dfs["leases"][c] = pd.to_datetime(dfs["leases"][c])
    return Store(**dfs)


def run_sql(query: str, limit: int = 200) -> pd.DataFrame:
    """Read-only SQL over the precomputed tables (for the agent's ad-hoc questions)."""
    q = query.strip().rstrip(";")
    if not q.lower().startswith(("select", "with")):
        raise ValueError("only SELECT queries are allowed")
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        return con.execute(f"SELECT * FROM ({q}) LIMIT {int(limit)}").df()
    finally:
        con.close()
