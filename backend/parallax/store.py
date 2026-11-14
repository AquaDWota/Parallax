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

TABLES = ["buildings", "captures", "car_counts", "leases", "usage", "tenancies"]


@dataclass
class Store:
    buildings: pd.DataFrame
    captures: pd.DataFrame
    car_counts: pd.DataFrame
    leases: pd.DataFrame
    usage: pd.DataFrame
    tenancies: pd.DataFrame
    _events: dict = field(default_factory=dict)

    def occupancy_panel(self) -> pd.DataFrame:
        if "occ" not in self._events:
            from .occupancy import build_panel
            self._events["occ"] = build_panel(self.buildings, self.usage, self.tenancies)
        return self._events["occ"]

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
        from .occupancy import tenancies_from_leases
        d = generate()
        buildings, captures, car_counts, leases = d.buildings, d.captures, d.car_counts, d.leases
        tenancies = tenancies_from_leases(leases)
    else:
        from .loaders import load_real, load_tenancies
        buildings, captures, car_counts, leases = load_real()
        tenancies = load_tenancies(buildings.building_id)
    usage = compute_usage(buildings, captures, car_counts)
    con = duckdb.connect(str(config.DB_PATH))
    for name, df in dict(buildings=buildings, captures=captures, car_counts=car_counts,
                         leases=leases, usage=usage, tenancies=tenancies).items():
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()
    get_store.cache_clear()
    return Store(buildings, captures, car_counts, leases, usage, tenancies)


def _inputs_newer_than_db() -> bool:
    """Real mode: rebuild when any input CSV changed after the database was built (e.g. a new batch run)."""
    if config.DATA_MODE != "real" or not config.DB_PATH.exists():
        return False
    db_time = config.DB_PATH.stat().st_mtime
    names = ["car_counts.csv", "captures.csv", "vexcel_buildings.csv", "costar_properties.csv",
             "costar_leases.csv", "costar_occupancy.csv"]
    return any((config.DATA_DIR / "real" / n).exists() and (config.DATA_DIR / "real" / n).stat().st_mtime > db_time
               for n in names)


@lru_cache(maxsize=1)
def get_store() -> Store:
    if not config.DB_PATH.exists() or _inputs_newer_than_db():
        if config.DB_PATH.exists():
            print("data files changed since the last build - rebuilding the database")
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
    for c in ["from_date", "to_date"]:
        dfs["tenancies"][c] = pd.to_datetime(dfs["tenancies"][c])
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
