"""Precompute everything (the batch job): python -m scripts.build"""
from parallax import analysis, config, store

if __name__ == "__main__":
    s = store.build()
    ev, excl = s.events(0)
    print(f"mode={config.DATA_MODE}  buildings={len(s.buildings)}  captures={len(s.captures)}  leases={len(s.leases)}")
    print("exclusions:", excl)
    result = analysis.logistic(ev)
    print(result.get("interpretation") or f"Regression unavailable: {result.get('error', 'no interpretation returned')}")
    print(f"wrote {config.DB_PATH}")
