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
# Which detector's counts real mode uses: car_counts.csv (Vexcel sam3, default) or car_counts_yolo.csv.
CAR_COUNTS_FILE = os.environ.get("PARALLAX_CAR_COUNTS", "car_counts.csv")
_db_tag = "" if CAR_COUNTS_FILE == "car_counts.csv" else "_" + Path(CAR_COUNTS_FILE).stem
_db_tag += "" if os.environ.get("PARALLAX_EXCLUDE", "1") == "1" else "_allbuildings"
DB_PATH = DATA_DIR / f"parallax_{os.environ.get('PARALLAX_DATA_MODE', 'synthetic')}{_db_tag}.duckdb"

DATA_MODE = os.environ.get("PARALLAX_DATA_MODE", "synthetic")
MODEL = os.environ.get("PARALLAX_MODEL", "anthropic:claude-sonnet-5-5")
VEXCEL_API_KEY = os.environ.get("VEXCEL_API_KEY", "")

# Usage-index parameters (see "Car counting and the usage index" in the plan)
PEER_RADIUS_KM = 2.0
# Synthetic data has 2 captures/yr from 2018. Real Vexcel data has ~1/yr from 2016-17,
# so real mode uses a wider pre-COVID baseline and wider predictor windows.
REAL = DATA_MODE == "real"
BASELINE_YEARS = (2016, 2019) if REAL else (2018, 2019)
# Baseline = captures in [start, end). Real Houston has a Feb 2020 capture that is pre-COVID.
BASELINE_RANGE = ("2016-01-01", "2020-03-01") if REAL else ("2018-01-01", "2020-01-01")
# Real data: neighbours of unknown type (discovered parcels) count as peers, so compare across types.
PEER_BY_TYPE = not REAL
# Real data: small lots make the index jumpy - require a baseline of at least this many cars.
MIN_BASELINE_CARS = 8 if REAL else 0
# Off-day filter: a photo is dropped as an off day (weekend / holiday / storm) when the lot is below
# OFF_DAY_RATIO of its own usual fill AND the median neighbour in the same flight is too. Vexcel only
# gives a flight's date range (median ~24 days), not the day each building was shot, so the
# neighbours stand in for the calendar. Set PARALLAX_OFF_DAY=0 to switch it off and compare.
OFF_DAY_FILTER = os.environ.get("PARALLAX_OFF_DAY", "1") == "1"
# Buildings listed in data/real/exclude_buildings.csv (badly outlined lots, from scripts.clip_lots) are left out
# as not measurable. PARALLAX_EXCLUDE=0 puts them back, to report results both ways.
EXCLUDE_LISTED = os.environ.get("PARALLAX_EXCLUDE", "1") == "1"
# Calendar filter (runs first, when data/real/photo_dates.csv exists): Vexcel's raw-photo search gives
# the exact day each building was shot. Measured on the real counts (cars vs the lot's usual):
# weekdays 1.05x, Sundays 0.69x, Jan 1 0.50x, Saturdays 0.96x (offices ~normal, industrial/flex low).
# So Sundays and federal holidays are dropped for every building, Saturdays only for SATURDAY_CLOSED.
# Flights whose photos span different kinds of day ("mixed") or have no date fall through to the
# neighbour check above. PARALLAX_CALENDAR=0 switches it off.
CALENDAR_FILTER = os.environ.get("PARALLAX_CALENDAR", "1") == "1"
SATURDAY_CLOSED = {"industrial", "flex"}
OFF_DAY_RATIO = 0.5            # "low" = below half the lot's usual fill
OFF_DAY_MIN_PEERS = 3          # neighbours needed in the same flight; fewer -> same-year fallback
INDEX_CAP = 300.0
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
