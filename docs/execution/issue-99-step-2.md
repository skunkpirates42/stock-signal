# Step 2: local next-bar-open entries

Implements [#95](https://github.com/skunkpirates42/stock-signal/issues/95) after
PRs #100 and #101, baseline `e4b6ddb`. Alpaca bracket work remains separate.

## Policy

Local pending entries use the next observed five-minute bar's open and timestamp.
Stop/target levels stay anchored to the signal. An open at or beyond either level
rejects the entry using the existing broker risk-level guard, for both directions.
Valid entries receive protective checks on the entry bar; stop wins a two-level
touch. The entry bar counts once, costs apply once per side, and exit timestamps
remain the bar's close because OHLC cannot identify the intrabar touch time.

Open allocations run alphabetically before any intrabar exits, so later exits
cannot fund earlier entries. Accounting cash known after the open is posted after
that batch and cannot fund its entry. Same-session, stale-candidate and flatten
rules retain their previous eligibility: the next observed start must be zero to
five minutes after the signal's logical decision timestamp. One missing bucket is
therefore allowed; older candidates are discarded. The existing conservative
close-based flatten cutoff is retained, including early-close sessions. A symbol
that exits cannot queue another candidate on that bar.

`fill_policy=next_5min_open_signal_levels_v1` identifies new artifacts. The existing
exit policy remains `touching_bar_level_or_gap_open_stop_first_v1`. Alpaca still
submits at decision time and records broker fills. Frozen shadow runs retain their
own close-fill policy; historical results and their labels are not rewritten.

The live engine observes completed bars after the lateness allowance. The next
bar's open is a **simulated reference price**, potentially preceding actual signal
availability by that allowance. This change does not make fills immediate in wall
clock time or establish that a real order could have filled at that price.

## Fixture comparison

Both runs use `backtest.py --dataset tests/fixtures/bars.json` with separate scratch
databases and output directories `/tmp/stock-signal-95-{before,after}-report`.

| Metric | Merged step 1 | Step 2 | Explanation |
| --- | ---: | ---: | --- |
| Closed / open trades | 28 / 2 | 28 / 2 | Same fixture trade population. |
| Win rate | 53.6% (15W / 13L) | 53.6% (15W / 13L) | Same stop/target outcomes. |
| Average win / loss | +98.84 / −78.78 | +111.87 / −72.71 | Open reference prices change payoffs and sizing. |
| Expectancy | +16.37 | +26.17 | Revised per-trade payoffs. |
| Profit factor | 1.448 | 1.775 | Winning and losing P&L totals change. |
| Total P&L | +458.46 | +732.78 | Earlier entry reference prices change fixture economics. |
| Max drawdown | 367.30 (0.364%) | 314.29 (0.312%) | Changed realized-equity path. |
| Average bars held | 8.3 | 9.3 | Entry bar now counts. |
| Mean realized R | +0.808 | +0.607 | Signal levels now align with entry prices in this fixture. |
| Winning / losing R | +2.374 / −1.000 | +2.000 / −1.000 | Fixture opens coincide with signal prices; no general 2R guarantee. |

The expected metrics snapshot includes full equity and ticker/regime breakdowns.
These synthetic data validate execution semantics, not strategy profitability.

## Verification

Regression coverage includes distinct open/close prices, persisted entry timestamp,
LONG/SHORT entry-bar target and stop-first ties, crossed-level rejection, costs,
restart/duplicates, stale/future/session/early-close guards, allocation before
intrabar exit proceeds and accounting cash availability. Full backend results,
independent review and live evidence are recorded when completed.
