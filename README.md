# stock-signal

A rule-based intraday trading signal engine, built to find out whether a transparent
consensus-of-indicators strategy can survive real trading costs.

The repository implements the research plumbing; it does not establish a validated
trading edge. Earlier numerical findings below are historical and unverified: their
original dataset and exact gate configuration are not available in this checkout.

**No real capital has been traded. This is not investment advice.**

## What it does

Every five minutes, for each ticker on the watchlist, six directional indicators vote.
If at least 62% agree, the engine emits LONG or SHORT with a stop and a target at a
designed 2:1 reward-to-risk; otherwise it emits WAIT. The trading decision is a pure
function and is unit tested. An LLM writes the human-readable rationale for a signal but
never makes or influences the call.

Every signal and every outcome is written to SQLite, so the strategy is judged on its
logged record rather than on memory.

## Architecture

| Area | Path | What it does |
|---|---|---|
| Signal engine | `signals/` | Six indicator votes plus a volume modifier; consensus threshold decides direction. Pure, tested. |
| Market data | `data/` | Alpaca IEX bars: REST for history, websocket for live, aggregated to 5-minute. Seeded synthetic fallback so it runs fully offline. |
| Execution | `trades/` | Local fill simulator by default; real Alpaca paper orders with `BROKER=alpaca`. Restart-safe. |
| Backtest | `backtest.py` | Replays saved or fetched bars chronologically through the shared local simulation pipeline. |
| Dashboard API | `dashboard/` | Flask app exposing `/api/metrics`, `/api/signals`, `/api/trades`, `/api/open`, `/api/alerts` over `analytics/metrics.py` and SQLite. Also still serves a legacy templated page at `/`. |
| Dashboard UI | `web/` | Next.js 16 / React 19 app ("Instrument") — Overview, Signals and Positions pages, reading the Flask API. Dark, mono-numeral instrument-panel design; equity curve, win/loss, cost-adjusted expectancy, R-multiples, by-ticker/regime breakdowns. This is the primary dashboard going forward. |
| Alerts | `alerts/` | Live alert feed with browser and native macOS notifications. |
| Persistence | `db/` | SQLite log of every signal and trade. |

Replay and local live simulation share the same bar pipeline. Local fills use the next
completed five-minute bar's close, a deliberately delayed simulation policy. Alpaca paper
orders use confirmed market fills and therefore have different execution latency.
Neither mode places protective stop/target orders at the broker.

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

Tests:

```bash
.venv/bin/python -m pytest tests/ -q   # backend
cd web && pnpm test                    # frontend (vitest)
```

## Historical findings — unverified

These are archived claims, not reproduced by the corrected implementation. The original
data/configuration are missing and the old replay had chronology and fill-model defects.
The new gates have explicit definitions in `signals/quality.py`; they are separate
experiments, disabled in the default live engine.

The original report attributed the figures below to one backtest window of roughly three months of Alpaca IEX
5-minute bars across eight mega-cap tickers — 2,464 closed trades.

**1. Historical gross expectancy claim.**

A 35.6% win rate at 2:1 reward-to-risk produces a small positive gross expectancy of
**+$2.94 per trade**. It is positive for both longs and shorts and in every market
regime, so it is not merely long bias in a rising market. But the entire edge is roughly
what realistic spread plus exit slippage costs. Net of about $3 per trade in friction it
is break-even to negative. Not tradeable as it stands.

**2. Demanding more agreement makes it worse.**

The obvious fix is to take fewer, higher-conviction trades. It backfires. Tightening the
threshold from 4 votes to 5 cut trade count roughly eightfold *and* collapsed per-trade
expectancy to +$0.86. The six indicators are all price-derived and therefore collinear —
"strong consensus" mostly means a late, extended entry. The conviction knob is exhausted;
the current threshold is already the sweet spot.

**3. Orthogonal information does what conviction could not.**

Keeping the direction call unchanged and adding a quality gate from information the votes
do not contain:

| Gate | Trades | Win % | Expectancy | Net @ $3/trade |
|---|---|---|---|---|
| Baseline, no gate | 2,464 | 35.6% | +$2.94 | −$144 |
| Relative strength vs SPY | 1,990 | 36.1% | +$3.62 | +$1,235 |
| RVOL ≥ 1.5 | 1,215 | 36.2% | +$3.76 | +$921 |
| Both | 930 | 37.1% | +$5.97 | +$2,761 |

Both gates are computed causally, with no look-ahead. Relative strength alone clears the
cost line; pairing it with real volume roughly doubles per-trade edge.

### What these numbers are not

This is a single in-sample window on partial-volume IEX data with idealized exits, and
the best gate combination was chosen by looking at that same window. It demonstrates
working plumbing and a promising direction. It does **not** demonstrate a validated edge.

Before any of it means anything: walk-forward testing on periods the gates were not tuned
on, modeled spread and realistic exit fills instead of a flat cost proxy, and then forward
paper trading for 50+ trades across mixed regimes.

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
.venv/bin/python research.py --dataset tests/fixtures/bars.json --windows tests/fixtures/windows.json --output /tmp/gate-comparison
```

Artifacts include configuration, dataset/code fingerprints, feed, policy, historical
trades, metrics and a report. Fixture results validate plumbing only. Real research needs
saved market data, fixed development/holdout windows, realistic cost scenarios and
prospective validation. RVOL needs at least ten prior session observations; the small
fixture intentionally cannot establish a volume result.

Next.js polls while visible and preserves filters/explanation state. The status band
separates API reachability from worker heartbeat/data freshness and exposes unresolved
orders. Overview P&L is net of recorded costs; the cost input applies an **additional**
hypothetical cost. Legacy rows may lack modeled costs. The legacy Flask dashboard remains
available, but the Next.js dashboard is the operational interface.

See [paper smoke-test procedure](docs/paper-smoke-test.md) before an opt-in connected test.
