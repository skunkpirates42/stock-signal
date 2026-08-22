# stock-signal

A rule-based intraday trading signal engine, built to find out whether a transparent
consensus-of-indicators strategy can survive real trading costs.

The short answer so far: it has a genuine, direction-agnostic edge that is too thin to
clear costs on its own, and a single orthogonal filter appears to push it into the black.
That result is a promising lead from one in-sample window, not a validated strategy.
See [Findings](#findings) for the numbers and the caveats.

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
| Backtest | `backtest.py` | Replays months of real bars through the identical engine, executor and exit logic as the live path. |
| Dashboard | `dashboard/` | Flask app: equity curve, expectancy, drawdown, breakdowns by ticker and regime. |
| Alerts | `alerts/` | Live alert feed with browser and native macOS notifications. |
| Persistence | `db/` | SQLite log of every signal and trade. |

Backtest and live share the same engine, executor and exit code, so their results are
directly comparable. That was a deliberate constraint from the start — a backtest that
runs different code from the live path measures the wrong thing.

## Running it

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

cp .env.example .env          # optional: only needed for real data and LLM rationales
.venv/bin/python poc.py       # runs fully offline against synthetic data
.venv/bin/python backtest.py  # replay historical bars
.venv/bin/python run_dashboard.py
```

Tests:

```bash
.venv/bin/python -m pytest tests/ -q
```

## Findings

All figures below come from one backtest window of roughly three months of Alpaca IEX
5-minute bars across eight mega-cap tickers — 2,464 closed trades.

**1. The edge is real but thinner than costs.**

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
