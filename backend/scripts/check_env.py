"""Diagnose key loading: python -m scripts.check_env"""
import os

from parallax import config

p = config.ENV_PATH
print("looking for:", p)
print(".env exists:", p.exists())
if not p.exists():
    near = [f.name for f in config.REPO_ROOT.iterdir() if f.name.startswith(".env") or f.name.endswith(".env")]
    print("similar files in repo root:", near or "none")
    print("also check backend/:", [f.name for f in (config.REPO_ROOT / "backend").iterdir() if ".env" in f.name])
else:
    keys = [l.split("=", 1)[0].strip() for l in p.read_text(encoding="utf-8-sig").splitlines() if "=" in l and not l.strip().startswith("#")]
    print("variables in .env:", keys)
v = os.environ.get("VEXCEL_API_KEY", "")
print("VEXCEL_API_KEY loaded:", f"yes ({len(v)} chars, starts {v[:4]})" if v else "NO")
