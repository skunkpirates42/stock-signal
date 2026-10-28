# Step 1: local touching-bar exits

Implements the local portion of [#97](https://github.com/skunkpirates42/stock-signal/issues/97)
in the sequence from [#99](https://github.com/skunkpirates42/stock-signal/issues/99).
The baseline was reproduced on `main` at `1b182a1` on October 28, 2026.
Issue #97 remains open for the later Alpaca bracket-order step.

## Execution policy

Local replay and `LiveTrader` now close an existing position on the observed bar
whose range touches its stop or target. `check_exit` still selects the stop when
both levels are touched. The reference fill is that selected level, or the bar's
open when it is beyond that level in the exit direction. Stop-first also applies
when the open is beyond the target and the range later reaches the stop: the
conservative stop fill wins. Costs still apply once to entry and exit.

The exit timestamp is the touching bar's decision time (start plus five minutes).
The touching bar counts once toward `bars_held`. Protective exits precede
close-time flatten and can fill within the final regular-hours bar. They are
simulated intrabar fills, not broker-observed executions.

Entries still fill at the next completed bar's close; the entry bar's earlier
range cannot trigger an exit. No candidate is queued or filled on an exit bar.
Session flatten remains at an observed executable close before session end;
unresolved session exits wait for a later executable close. Restored legacy
pending exits retain their close-fill fallback if the new bar has no touch.

The manifest retains `fill_policy=next_completed_5min_close` for entries and adds
`exit_policy=touching_bar_level_or_gap_open_stop_first_v1` and an explicit session
exit policy. The exported report states all three policies. Existing saved runs
and the separately frozen `research/shadow.py` experiment are unchanged. Alpaca
continues to use confirmed broker fills; bracket changes belong to step 4.

## Fixture comparison

Both runs used:

```sh
.venv/bin/python backtest.py --dataset tests/fixtures/bars.json --db <scratch>.db --output <scratch>-report
```

| Metric | Baseline | Step 1 | Explanation |
| --- | ---: | ---: | --- |
| Closed / open trades | 19 / 3 | 28 / 2 | Earlier exits free positions for subsequent candidates. |
| Win rate | 52.6% (10W / 9L) | 53.6% (15W / 13L) | Touch prices and the subsequent trade population change outcomes. |
| Average win / loss | +89.25 / −109.65 | +98.84 / −78.78 | Level fills remove delayed-close drift; sizes and trade population also change. |
| Expectancy / trade | −4.96 | +16.37 | Changed outcomes and payoff sizes increase average net P&L. |
| Profit factor | 0.904 | 1.448 | Aggregate winning P&L increases relative to losing P&L. |
| Total P&L | −94.30 | +458.46 | Earlier level fills and additional trades change realized results. |
| Max drawdown | 465.86 (0.464%) | 367.30 (0.364%) | The revised realized-equity path has a smaller peak-to-trough loss. |
| Average bars held | 10.3 | 8.3 | No extra exit-delay bar; subsequent trades also differ. |
| Mean realized R | +0.775 | +0.808 | Changed payoff ratios and outcome mix. |
| Winning / losing R | +2.517 / −1.159 | +2.375 / −1.000 | All 13 stops and 15 targets fill exactly at their levels; none gap in this fixture. |

Winning R need not equal 2: entries still occur at a later close while keeping the
signal's original stop and target. Step 2 addresses entry timing separately.
The snapshot was regenerated from this run, including ticker/regime breakdowns
and the full realized-equity path. These synthetic fixture results check execution
semantics; they do not establish strategy profitability.

Local artifacts: `/tmp/stock-signal-99-before-report` and
`/tmp/stock-signal-99-final-report`, each with its own scratch database, manifest,
input dataset, trades and metrics. No existing run artifacts were overwritten.

## Verification

Regression cases cover LONG and SHORT stops, targets, adverse/favorable gaps,
stop-first ties (including a target-side gap), ordinary/flatten/final-session bars,
costs, persisted timestamps, observed-bar counts, restart and duplicate processing.
An explicit entry-range regression preserves close-entry chronology.

The fixture exposed simultaneous exits ordered by trade ID in the dashboard but
by ticker in replay. The database metrics loader now uses timestamp, ticker, ID,
matching replay's deterministic execution order. The existing dashboard snapshot
regression checks the complete equity path as well as aggregate metrics.

A bounded live check on October 28 at 14:17 EDT used `BROKER=local`, template
synthesis and `/tmp/stock-signal-99-live.db`. The initial sandbox attempt failed
DNS resolution. With network access the market clock reported OPEN, all eight
symbols seeded, and the stream subscribed. The process stopped after 45 seconds;
no open/close event occurred. This verifies startup only: observing an actual
live touching-bar exit remains an outstanding acceptance check. No broker orders
were submitted and no unattended collector was left running.

Final checks: 79 focused correctness tests passed; the full backend suite passed
427 tests (two dependency warnings: LibreSSL/urllib3 and deprecated websockets).
`git diff --check` passed. Final exported metrics equal the regenerated snapshot,
and the exported manifest/report both identify the new exit policy. No UI files
changed, so frontend checks were not required.
