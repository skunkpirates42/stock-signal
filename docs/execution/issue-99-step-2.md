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
| Max drawdown | 367.30 (0.364%) | 314.29 (0.311%) | Changed realized-equity path. |
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

## Independent review

Separate spec and standards agents reviewed `e4b6ddb...33e7862` read-only.
Neither found a material implementation defect. Both identified the stale trader
module description; standards also noted the accounting-posting helper description.
Both docstrings were corrected. The spec reviewer used the supplied issue requirements
and tracked policy because its GitHub network request failed. Reviews did not rerun
tests. Historical results/interview documents named by #95 are ignored local files;
they were updated locally without publishing their preexisting contents in this PR.
The tracked policy and accounting-contract update explain the historical distinction.

Final fixed-revision validation: **446 backend tests passed**, with only the existing
LibreSSL/urllib3 and websockets deprecation warnings. `git diff --check` passed.
No UI changes require frontend checks. An earlier full run encountered the demo
worker's strategy-version guard because a commit occurred during the suite; the
isolated test and complete rerun with a stable revision both passed. The new
accounting regression also initially needed a Decimal comparison rather than a
formatted string comparison. No demo-worker application change was needed.
Both reviewers confirmed their documentation findings resolved.

## Completed live acceptance: October 28, 2026

The bounded IEX capture ran from 15:41:56 to approximately 15:55:39 EDT with
`BROKER=local`, the existing overnight session policy, a scratch SQLite database
and broker submission explicitly disabled. The initial partial bucket was dropped;
natural deterministic signals from the 15:45–15:50 bucket queued entries.

TSLA LONG filled at **403.61**, the 15:50–15:55 bar's **open**, with
`entry_at=2026-10-28T19:50:00+00:00`. Its signal stop **402.2134** and target
**406.5832** were retained. The fill was observed after 15:55:35, not at wall-clock
15:50: this proves the simulation reference price and timestamp, not broker latency.

The verifier rebuilt the complete entry bar from five received minute bars and
checked saved entry fields, signal levels, live/local scope and zero order rows.
The process stopped automatically; scratch positions are hypothetical only.
[Captured evidence](evidence/issue-95-live-2026-10-28.json) includes the raw minutes,
bar, saved trade/signal and artifact hashes. Full scripts, seed and journal remain
in `/tmp/stock-signal-95-live/`. The capture began on the merged baseline plus the
working execution patch (diff hash recorded), subsequently committed in `33e7862`;
later runtime-file edits corrected docstrings only.

A final replay at `6c716dd` exactly matches the regenerated snapshot. All 30 trades
retain the previous fixture's ticker, direction, signal levels and outcome.
