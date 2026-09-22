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

## Historical findings — unverified

These are archived claims, not reproduced by the corrected implementation. The original
data/configuration are missing and the old replay had chronology and fill-model defects.
The new gates have explicit definitions in `signals/quality.py`; they are separate
experiments, disabled in the default live engine.

The original report attributed the figures below to one backtest window of roughly three months of Alpaca IEX
5-minute bars across eight mega-cap tickers — 2,464 closed trades.

**1. Historical gross expectancy claim.**

The old report claimed a 35.6% win rate and **+$2.94 gross expectancy per trade**.
It also claimed positive gross expectancy across sides and regimes. Those breakdowns
cannot be independently reproduced from the missing source artifacts. A flat $3/trade
cost proxy would have erased the reported edge.

**2. Demanding more agreement makes it worse.**

The old report said increasing consensus from four to five votes reduced trade count
roughly eightfold and gross expectancy to +$0.86/trade. Overlapping price-derived votes
could explain why more agreement did not help, but this result cannot establish an
optimal threshold.

**3. Orthogonal information does what conviction could not.**

Keeping the direction call unchanged and adding a quality gate from information the votes
do not contain:

| Gate | Trades | Win % | Expectancy | Net @ $3/trade |
|---|---|---|---|---|
| Baseline, no gate | 2,464 | 35.6% | +$2.94 | −$144 |
| Relative strength vs SPY | 1,990 | 36.1% | +$3.62 | +$1,235 |
| RVOL ≥ 1.5 | 1,215 | 36.2% | +$3.76 | +$921 |
| Both | 930 | 37.1% | +$5.97 | +$2,761 |

These are the old report's figures under a flat cost proxy. Its exact gate definitions
and original data are missing; do not compare this table directly with the completed
`quality_v2` experiment above.

### What these numbers are not

This was a single in-sample window on partial-volume IEX data with idealized exits, and
the best combination was selected after viewing it. The archived numbers do **not**
demonstrate a validated edge. The later saved experiment has a separate, explicit
protocol, but it does not rehabilitate these missing artifacts.

## Status

Personal research project, in validation. Not a product, not advice, and no real money
has been at risk.

## Corrected execution and research workflow

Configuration loads `.env` from the repository root before settings are read. Defaults:
`papertrader.db` for live/PoC and `backtest.db` for replay. An explicit `DB_PATH` overrides
both; source/backend/account filtering still prevents automatic replay restoration.
New databases initialize automatically for dashboard and report commands.

Live order intents, IDs and cumulative fills are durable. Uncertain requests remain
unresolved and block new entries until reconciled; they are never replaced by theoretical
fills. Remaining exposure survives partial fills and restart. Unknown legacy positions
require an evidence-backed mapping (`scripts/tag_existing_sources.py --help`). A failed
account query is an error, not an empty account. All runtime broker calls run on one
worker; websocket ingestion only queues events.

Replay processes all symbols chronologically, exits before alphabetical entry allocation,
with an unlevered gross-exposure cap. Signals include WAIT and explicit skip reasons.
Historical fill timestamps drive the equity curve; audit insertion timestamps remain
separate. Dataset-end positions are censored, not force-closed. Modeled costs are stored
separately from gross P&L; `pnl` is net. `BREAKEVEN` is a valid realized outcome, and stop/
target trigger reason is separate from outcome.

`SESSION_POLICY=overnight` preserves open exposure across sessions. `flatten` attempts
closure five minutes before the exchange close, including early closes. Failed/missing
fills retain exposure. Complete five-minute live buckets finalize on a clock after a
35-second allowance; missing minutes do not become fabricated bars. The pinned XNYS
calendar supplies session boundaries; extraordinary closures require calendar maintenance.

Reproduce the synthetic fixture (no credentials or network):

```bash
.venv/bin/python backtest.py --dataset tests/fixtures/bars.json --db /tmp/fixture.db --output /tmp/fixture-report
```

Compare optional research gates on explicitly labeled chronological windows:

```bash
.venv/bin/python research.py --dataset tests/fixtures/bars.json --windows tests/fixtures/windows.json --output /tmp/gate-comparison --allow-synthetic --allow-zero-costs
```

Artifacts include configuration, dataset/code fingerprints, feed, policy, historical
trades, metrics and a report. Fixture results validate plumbing only. Real research needs
saved market data, fixed development/holdout windows, realistic cost scenarios and
prospective validation. RVOL needs at least ten prior session observations; the small
fixture intentionally cannot establish a volume result.

`python -m analytics.research_review --comparison <output>` adds marked open-position
equity, drawdown, exposure, turnover and paired session-block uncertainty to a completed
comparison. Dividends and short borrow remain unmodeled.

Next.js polls while visible and preserves filters/explanation state. The status band
separates API reachability from worker heartbeat/data freshness and exposes unresolved
orders. Overview P&L is net of recorded costs; the cost input applies an **additional**
hypothetical cost. Legacy rows may lack modeled costs. The legacy Flask dashboard remains
available, but the Next.js dashboard is the operational interface.

See [paper smoke-test procedure](docs/paper-smoke-test.md) before an opt-in connected test.
