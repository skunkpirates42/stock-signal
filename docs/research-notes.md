# Research notes

Execution rules, research workflow and archived findings, moved here from the README.

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

See [paper smoke-test procedure](paper-smoke-test.md) before an opt-in connected test.

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
