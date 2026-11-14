"""Paths and settings. Everything reads from environment variables (.env at repo root)."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:  # dotenv is optional
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("PARALLAX_DATA_DIR", REPO_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "parallax.duckdb"

DATA_MODE = os.environ.get("PARALLAX_DATA_MODE", "synthetic")
MODEL = os.environ.get("PARALLAX_MODEL", "anthropic:claude-sonnet-5-5")
VEXCEL_API_KEY = os.environ.get("VEXCEL_API_KEY", "")

# Usage-index parameters (see "Car counting and the usage index" in the plan)
PEER_RADIUS_KM = 2.0
BASELINE_YEARS = (2018, 2019)
DROP_THRESHOLD = 85.0          # index below this counts as a drop
DROP_MIN_CAPTURES = 2          # ... only if it persists this many captures
SQM_PER_STALL = 30.0

# Correlation study
PREDICTOR_WINDOW_MONTHS = 12
LEAD_TIMES_MONTHS = (0, 6, 12, 18)
OOS_TRAIN_YEARS = (2019, 2022)
OOS_TEST_YEARS = (2023, 2026)


def llm_available() -> bool:
    provider = MODEL.split(":", 1)[0]
    key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "bedrock": "AWS_ACCESS_KEY_ID",
        "bedrock_converse": "AWS_ACCESS_KEY_ID",
    }.get(provider)
    return bool(key_env and os.environ.get(key_env))
