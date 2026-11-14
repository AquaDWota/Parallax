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
    usage_index.py   fill rate -> peer-normalized -> % of 2018-19 baseline -> smoothed + drop flags
    events.py        lease-expiry table: outcome + usage before expiry + controls
    analysis.py      usage bins, logistic regression, lead time, OOS AUC, placebo, COVID, noise, subgroups
    tools.py         the agent's tools (JSON in/out, chart-ready)
    agent.py         deepagents planner + helper sub-agents; scripted fallback with the same events
    store.py         batch precompute into DuckDB
  api/main.py        FastAPI: /api/meta, /api/buildings, /api/results/overview, /api/ask (SSE), /api/tools/{name}
  scripts/           build.py, probe_vexcel.py
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
