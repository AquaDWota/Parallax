"""Paths and settings. Everything reads from environment variables (.env at repo root)."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"


def _load_env(path: Path) -> None:
    """Minimal .env loader (no dependency). Fills variables that are unset OR empty in the shell."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and not os.environ.get(k):
            os.environ[k] = v


_load_env(ENV_PATH)
DATA_DIR = Path(os.environ.get("PARALLAX_DATA_DIR", REPO_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "parallax.duckdb"

DATA_MODE = os.environ.get("PARALLAX_DATA_MODE", "synthetic")
MODEL = os.environ.get("PARALLAX_MODEL", "anthropic:claude-sonnet-5-5")
VEXCEL_API_KEY = os.environ.get("VEXCEL_API_KEY", "")

# Usage-index parameters (see "Car counting and the usage index" in the plan)
PEER_RADIUS_KM = 2.0
# Synthetic data has 2 captures/yr from 2018. Real Vexcel data has ~1/yr from 2016-17,
# so real mode uses a wider pre-COVID baseline and wider predictor windows.
REAL = DATA_MODE == "real"
BASELINE_YEARS = (2016, 2019) if REAL else (2018, 2019)
DROP_THRESHOLD = 85.0          # index below this counts as a drop
DROP_MIN_CAPTURES = 2          # ... only if it persists this many captures
SQM_PER_STALL = 30.0

# Correlation study
PREDICTOR_WINDOW_MONTHS = 18 if REAL else 12
LEAD_TIMES_MONTHS = (0, 12, 24) if REAL else (0, 6, 12, 18)
OOS_TRAIN_YEARS = (2019, 2022)
OOS_TEST_YEARS = (2023, 2026)


def llm_available() -> bool:
    provider = MODEL.split(":", 1)[0]
    key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google_genai": "GOOGLE_API_KEY",
        "bedrock": "AWS_ACCESS_KEY_ID",
        "bedrock_converse": "AWS_ACCESS_KEY_ID",
    }.get(provider)
    return bool(key_env and os.environ.get(key_env))
