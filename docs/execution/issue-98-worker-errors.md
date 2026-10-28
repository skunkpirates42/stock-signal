# Worker error visibility (#98)

This is the independent reliability track allowed to move earlier by issue #99.
It is based on `main` at `1b182a1`, separate from PR #100's local exit-policy change.

The worker now logs every exception with a traceback and records its type/message
and consecutive failure count. Durable broker recovery remains automatic, but no
longer clears failure visibility. Heartbeats and incomplete buckets keep reporting
`blocked` with the error, count and notice that the failed batch was not retried.
Only a later successful new batch clears the failure state, and only after durable
recovery has succeeded. Alpaca reconciliation remains a prerequisite for recovery.

The collapsed dashboard status includes a highlighted badge for nonrunning scopes,
so an API response and fresh heartbeat cannot hide a blocked trading worker.
The expanded detail still carries the exception and failure count.

## Verification

The original implementation failed the worker regression loop because no traceback
was logged and recovery plus heartbeat returned the status to `running`. Four UI
render cases also failed because nonrunning statuses were absent from the collapsed
summary. All now pass.

Final backend suite: 392 passed, 3 skipped, with two existing dependency warnings.
The skipped tests require ignored local Alpaca data or saved scenarios absent from
this clean worktree; portable fixtures passed. Frontend: 44 files / 308 tests passed
using installed Vitest directly (the pnpm launcher hung). Focused ESLint/Prettier,
Next route type generation, TypeScript and `git diff --check` passed.

Two independent read-only reviews checked standards and issue requirements.
The standards review found that incomplete buckets could overwrite error detail
before the next heartbeat. A focused regression reproduced it; commit `441a5c3`
fixes it. The reviewer confirmed resolution. The spec reviewer found no material
implementation defects or scope creep. Shutdown lifecycle limitations for workers
that outlive the join timeout predate this patch and remain separate.

The bundled-fixture replay uses unchanged trading logic and the original execution
policy on this independent branch. No strategy thresholds, fills or snapshots are
changed by #98. Live acceptance evidence is recorded separately below.


| Metric | main `1b182a1` | #98 | Change |
| --- | ---: | ---: | --- |
| Closed / open trades | 19 / 3 | 19 / 3 | None |
| Win rate | 52.6% (10W / 9L) | 52.6% (10W / 9L) | None |
| Average win / loss | +89.25 / −109.65 | +89.25 / −109.65 | None |
| Expectancy / trade | −4.96 | −4.96 | None |
| Profit factor | 0.904 | 0.904 | None |
| Total P&L | −94.30 | −94.30 | None |
| Max drawdown | 465.86 (0.464%) | 465.86 (0.464%) | None |
| Average bars held | 10.3 | 10.3 | None |
| Mean realized R | +0.775 | +0.775 | None |
| Winning / losing R | +2.517 / −1.159 | +2.517 / −1.159 | None |

The full exported metrics JSON equals the existing fixture snapshot, including
ticker/regime breakdowns and every realized-equity point. Output is preserved at
`/tmp/stock-signal-98-replay-report`, with its own scratch database. PR #100 has
different execution results; this branch deliberately contains only #98 and can
land independently, as permitted by #99.


## Completed manual live acceptance

On October 28, 2026, revision `441a5c3` ran with live IEX minute bars and
`BROKER=local` in `/tmp/stock-signal-98-direct/live.db`. Order submission was
explicitly disabled. The harness intentionally raised a known `ValueError`
inside indicator calculation for the completed 15:25–15:30 EDT batch.

The console captured a traceback through TradingWorker, tick, process_batch,
regime and indicator calculation. After automatic recovery and another heartbeat,
the status at 15:30:44 remained `blocked`, with the exception message,
`consecutive worker failures: 1`, and `failed batch not retried` in its detail.
The dashboard API returned that state. Rendering the actual StatusLine component
from that captured API response verified the highlighted blocked badge in the
collapsed summary and the exception/count in expanded detail. This was a component
render check, not a browser screenshot.

The bounded run then stopped cleanly, leaving runtime status `stopped` and zero
broker orders. Offline regressions verify subsequent successful-batch clearing;
the live run deliberately stopped after verifying persistent failure visibility.
[Captured evidence](evidence/issue-98-live-2026-10-28.json) includes the traceback,
status/API response, revision, shutdown result and hashes. The scratch database,
rendered HTML and manual harness artifacts remain under `/tmp/stock-signal-98-direct`.
