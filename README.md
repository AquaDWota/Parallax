# Parallax

Does an emptying parking lot predict a tenant leaving? Parallax measures how strongly
parking-lot usage (car counts from Vexcel aerial imagery, 2018-2026) predicts lease renewals
(CoStar lease outcomes) across every surface-lot building in Houston and LA, and how far ahead.

Project plan: https://claude.ai/artifact/1pLBTLmBYEC2VQyrCCyqmw

## Run it (synthetic data, no keys needed)

```bash
# backend
cd backend
pip install -r requirements.txt
python -m scripts.build              # precompute usage index + tables -> data/parallax.duckdb (~25 s)
uvicorn api.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

Tests: `cd backend && pytest -q`

Synthetic data has the same shape as the real data and a planted signal (tenants who leave
use the building less 6-24 months before expiry). The UI says "Synthetic data" in the top bar
until `PARALLAX_DATA_MODE=real`.

## Keys

Copy `.env.example` to `.env` at the repo root. **Never commit `.env`** (it's git-ignored, and so
is everything in `data/` - the hackathon data is licensed for the event only).

| Variable | Used for |
|---|---|
| `VEXCEL_API_KEY` | imagery + car detection |
| `ANTHROPIC_API_KEY` | the LLM planner (without it, a scripted planner runs the same tools) |
| `GOOGLE_API_KEY` | alternative LLM: `pip install langchain-google-genai`, `PARALLAX_MODEL=google_genai:gemini-2.5-flash` |
| `PARALLAX_MODEL` | any LangChain `provider:model`, default `anthropic:claude-sonnet-5-5` |
| `PARALLAX_DATA_MODE` | `synthetic` or `real` |
| `PARALLAX_AGENT` | `auto` (default) or `scripted` to force the deterministic planner for the demo |

## Step 1 with real data: probe Vexcel

```bash
cd backend
python -m scripts.probe_vexcel                          # 4 default office parks
python -m scripts.probe_vexcel --lat 29.78 --lon -95.63 --name my_building
```

For each spot it pulls the parcel, lists every historical collection covering it, runs
Vexcel's `car` detector (`/elements/detect`, sam3) on each collection and saves the orthos.
Output goes to `vexcel_output/` (git-ignored). This answers the deciding question: **how many
captures back to 2018 exist, and can we count cars on each?**

## Layout

```
backend/
  parallax/
    synthetic.py     Houston + LA buildings, captures, car counts, leases (same schema as real)
    loaders.py       real CoStar + Vexcel loaders (TODO once we see the extract)
    vexcel.py        Vexcel API 2.0 client (parcel, collections, ortho, car detection, embeddings)
    usage_index.py   fill rate -> off days dropped -> peer-normalized -> % of baseline -> smoothed + drop flags
    photo_days.py    which day a photo was taken: workday / saturday / sunday / holiday
    events.py        lease-expiry table: outcome + usage before expiry + controls
    analysis.py      usage bins, logistic regression, lead time, OOS AUC, placebo, COVID, noise, subgroups
    tools.py         the agent's tools (JSON in/out, chart-ready)
    agent.py         deepagents planner + helper sub-agents; scripted fallback with the same events
    store.py         batch precompute into DuckDB
  api/main.py        FastAPI: /api/meta, /api/buildings, /api/results/overview, /api/ask (SSE), /api/tools/{name}
  scripts/           build.py, probe_vexcel.py, batch_car_counts.py, fetch_photo_dates.py, fetch_images.py
frontend/            Next.js: map + capture "stalls" slider | agent reasoning | results
```

## Two indexes, on purpose

* **Peer-relative index** (per building, the predictor): lot fill / median fill of same-type
  buildings within 2 km in the same capture, as % of the building's own 2018-19 level. Cancels
  time of day, weekday and season, which two captures a year can't control - but also cancels
  market-wide shifts.
* **Absolute index** (map colors, regional time series): lot fill as % of the building's 2018-19
  fill. Keeps the 2020 drop and recovery; noisier capture to capture.

## Findings so far (synthetic - for wiring only, not results)

The pipeline recovers the planted signal and shows a story worth checking on real data: the link
is driven by tenants that lease a large share of their building. A tenant leasing <10% of a
building barely moves its lot.

## Real data (Vexcel + CoStar)

```bash
cd backend
# 1. CoStar kit files -> data/real/ : location-occupancy.jsonl, company-detail.jsonl, commercial-property.jsonl
python -m scripts.prepare_costar          # -> costar_properties.csv, costar_leases.csv, costar_buildings.csv
# 2. car counts per building per Vexcel collection (run on your laptop; resumable)
python -m scripts.batch_car_counts --buildings ../data/real/costar_buildings.csv --limit 400 --workers 4
# 3. exact day each photo was taken (~5 min, resumable) -> photo_dates.csv
python -m scripts.fetch_photo_dates
# 4. build and serve
PARALLAX_DATA_MODE=real python -m scripts.build
PARALLAX_DATA_MODE=real uvicorn api.main:app --port 8000
# 5. (optional, for an offline-proof demo) prefetch real lot images, with detected cars boxed
python -m scripts.fetch_images --boxes
```

All steps need `VEXCEL_API_KEY` in `.env` except 1 and 4. Steps 2 and 3 only need re-running for new
buildings (both skip what's already done). After new car counts, re-run step 4 (~30 s). Don't skip
step 3: without `photo_dates.csv` the build still works but silently falls back to the weaker
neighbour-only off-day filter.

Off days: a lot photographed on a Sunday or holiday looks empty without anyone leaving. Vexcel only
gives each flight's date range, but its raw-photo search (`oriented/query`) gives the exact day every
building was shot. On the real counts, Sundays show 0.69x a lot's usual cars and Jan 1 0.50x, while
Saturdays (offices) and Dec 31 look normal. So the build drops Sunday and federal-holiday photos for
every building, and Saturday photos for industrial and flex (`parallax/photo_days.py`). Flights whose
photos span different kinds of day, or have no date, go through a neighbour check instead: a low lot is
dropped only if the lots around it in the same flight were low too. `PARALLAX_CALENDAR=0` or
`PARALLAX_OFF_DAY=0` turn the two filters off for comparison. With both on, the occupancy link is +2.93
usage points per 10 points of occupancy (p=0.0002), up from +2.36 with the neighbour check alone.

Lot images: the building panel shows the real Vexcel crop of the lot for each capture. In real mode the
API fetches a missing image from Vexcel the first time it's opened and caches it in `data/imagery/`;
`scripts.fetch_images` fills the cache ahead of time. Open a building directly with `?b=<building_id>`,
e.g. `http://localhost:3000/?b=P240089`.

What real mode changes: captures are Vexcel collections (~1 a year 2016-2026), compared with peers
in the same city and campaign year; baseline is 2016 to Feb 2020; lots with a baseline under 8 cars are
dropped; garage buildings (from CoStar parking, or an empty newest lot) are excluded; lease outcomes
come from CoStar `expirationReason` (7/12 renewal, 8 shed space, 1/4/10/... moved out).

## Open-source car detector (branch `yolo-detector`)

A second car count from a pretrained Ultralytics YOLO OBB model (DOTA classes `small vehicle`, `large vehicle`), run on plain Vexcel ortho tiles resampled to 10 cm/px with confidence 0.10 (tuned on the worst disagreements: at 15 cm / 0.25 it missed dark and shaded cars). It's there to check the Vexcel sam3 counts. Settings live in `.env` (`PARALLAX_YOLO_*`).

```bash
pip install -r backend/requirements.txt          # adds ultralytics; first run downloads yolo11s-obb.pt
cd backend
python -m scripts.batch_yolo_counts --limit 50   # resumable; --building ID, --workers 3, --all-pairs
python -m scripts.compare_detectors              # r, median ratio, 20 biggest disagreements -> vexcel_output/compare/
python -m scripts.compare_detectors --images P239891 --capture n29w95-us-tx-houston-2025  # lot + sam3 (cyan) + YOLO (magenta)
PARALLAX_CAR_COUNTS=car_counts_yolo.csv python -m scripts.build   # run the whole pipeline on YOLO counts
```

Tiles are cached in `data/imagery_tiles/` (git-ignored) as PNG, because JPEG compression wipes out small cars. The YOLO build writes its own `parallax_real_car_counts_yolo.duckdb`, so the default sam3 database is never touched. Ultralytics is AGPL-3.0: fine for this hackathon, but check the licence before any public or commercial release.
## Excluded buildings

`data/real/exclude_buildings.csv` lists buildings whose automatic lot outline is mostly street: more than 20% of it lies outside property parcels (from `scripts.clip_lots`). They're treated like garage buildings, as not measurable. The rule was set before looking at the results. To include them again and compare, set `PARALLAX_EXCLUDE=0`; that build uses its own database.
## Display settings

The interface opens in a dark theme with the Results panel in the middle and the AI agent on the right. The **Display** button in the top bar switches the theme (dark, light, or follow the system), the panel order, and the text size (small, medium or large). Choices are saved in your browser.
