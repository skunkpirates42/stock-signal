# stock-signal

A rule-based intraday trading signal engine, built to find out whether a transparent
consensus-of-indicators strategy can survive real trading costs.

The repository implements a paper-only signal engine, replay, operational dashboard and
read-only Research catalog. It does not establish a validated trading edge. The current
saved comparison is summarized below; earlier numerical findings are historical and
unverified because their original dataset and exact gate configuration are unavailable.

**No real capital has been traded. This is not investment advice.**

## What it does

Every five minutes, for each ticker on the watchlist, six directional indicators vote.
If at least 62% agree, the engine emits LONG or SHORT with a stop and a target at a
designed 2:1 reward-to-risk; otherwise it emits WAIT. The trading decision is a pure
function and is unit tested. The live loop generates an offline template explanation;
the dashboard can request a richer LLM explanation on demand. Neither explanation can
make or change the trading decision.

Every signal and every outcome is written to SQLite, so the strategy is judged on its
logged record rather than on memory.

## Architecture

| Area | Path | What it does |
|---|---|---|
| Signal engine | `signals/` | Six indicator votes plus a volume modifier; consensus threshold decides direction. Pure, tested. |
| Market data | `data/` | Alpaca IEX bars: REST for history, websocket for live, aggregated to 5-minute. Seeded synthetic fallback so it runs fully offline. |
| Execution | `trades/` | Local fill simulator by default; real Alpaca paper orders with `BROKER=alpaca`. Restart-safe. |
| Backtest | `backtest.py` | Replays saved or fetched bars chronologically through the shared local simulation pipeline. |
| Dashboard API | `dashboard/` | Flask app exposing operational JSON reads, on-demand signal explanations and versioned saved-research reads. Also still serves a legacy templated page at `/`. |
| Dashboard UI | `web/` | Next.js 16 / React 19 app ("Instrument") — Overview, Signals, Positions, `/research` and `/runs/[runId]` saved-result audit pages. |
| Research artifacts | `demo/`, `docs/engine-demo/` | Imports reviewed saved bundles into a separate SQLite index; verifies an allowlist and hashes, then serves owner-scoped, read-only result and artifact views. |
| Alerts | `alerts/` | Live alert feed with browser and native macOS notifications. |
| Persistence | `db/` | SQLite log of every signal and trade. |

Replay and local live simulation share the same bar pipeline. Local fills use the next
completed five-minute bar's close, a deliberately delayed simulation policy. Alpaca paper
orders use confirmed market fills and therefore have different execution latency.
Neither mode places protective stop/target orders at the broker.
The Research pages display saved evidence and explicit unavailable values. They do not
submit backtests, activate strategies or provide hosted multi-tenancy.

## Running it

Backend (signal engine, backtest, dashboard API):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

cp .env.example .env          # optional: only needed for real data and LLM rationales
.venv/bin/python poc.py       # runs fully offline against synthetic data
.venv/bin/python backtest.py  # replay historical bars
.venv/bin/python run_dashboard.py   # serves the JSON API on http://127.0.0.1:8000
```

Dashboard frontend (separate process, talks to the Flask API above):

```bash
cd web
pnpm install
pnpm dev   # http://localhost:3000 (set FLASK_API_URL if the API isn't on the default port)
```

The operational pages are available with a local database. The Research catalog is empty
until a reviewed saved bundle is imported into its separate index. If you have the local
`research-output/alpaca-iex-2026-base-v2` bundle, a read-only demo can use:

```bash
PYTHONPATH=. .venv/bin/python -c 'from demo.artifacts import ArtifactIndex; ArtifactIndex("/tmp/stock-signal-artifacts.db").import_directory("research-output/alpaca-iex-2026-base-v2", owner_id="local")'
DEMO_ARTIFACT_DB_PATH=/tmp/stock-signal-artifacts.db .venv/bin/python run_dashboard.py
```

Then open `http://localhost:3000/research` in the running Next.js app. The saved market
bundle is local and gitignored; a fresh clone does not include it. The importer indexes
allowlisted result files, not raw bars or broker credentials. The [versioned read-model
contract](docs/engine-demo/README.md) describes the catalog and audit limitations.

Tests:

```bash
.venv/bin/python -m pytest tests/ -q   # backend
cd web && pnpm test                    # frontend (vitest)
```

## Saved research comparison

The completed January–August 2026 Alpaca IEX experiment compared the unchanged baseline,
benchmark-relative strength, time-of-day relative volume (RVOL) and both gates. January–
February supplied warmup history; development covered 84 March–June exchange sessions;
the named holdout covered 43 July–August sessions. “Adverse holdout” reruns that same
July–August period with higher modeled trading costs; it is not a third time window.

| Marked net P&L | Development, base costs | Holdout, base costs | Holdout, adverse costs |
| --- | ---: | ---: | ---: |
| Baseline | +$2,226.27 | +$412.68 | −$5,718.88 |
| Relative strength | +$3,855.20 | −$902.36 | −$5,311.27 |
| RVOL | −$970.92 | +$3,460.79 | −$105.35 |
| Both gates | +$1,490.52 | +$76.77 | −$2,490.78 |

The base scenario models 2 bps round-trip spread and 1 bp slippage per fill; adverse
models 5 bps and 2 bps respectively. These are declared assumptions, not measured
execution costs. Marked results include open positions valued at the latest completed
close and paid entry costs, without inventing an exit fill or fee. Dividends, short borrow
and actual quote spreads were not fully accounted for in these saved runs.

RVOL had the strongest base-cost holdout, but lost in development and was slightly
negative under adverse holdout costs. Its descriptive paired uncertainty interval for
the holdout advantage over baseline crossed zero. No variant was promoted. These are
retrospective results, and the viewed holdout cannot validate a revised strategy. The
reviewed result bundles and raw market bars are local, gitignored artifacts, so a fresh
clone cannot independently reproduce these figures. Next checks are complete cash-flow
accounting, execution-cost evidence and prospective baseline-versus-RVOL observations.

## Status

Personal research project, in validation. Not a product, not advice, and no real money
has been at risk.

Execution rules, the research workflow and archived findings are in [docs/research-notes.md](docs/research-notes.md).
