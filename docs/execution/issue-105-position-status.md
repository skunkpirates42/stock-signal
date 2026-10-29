# Issue 105: position provenance and broker observations

The positions page polls a read-only journal projection every five seconds while visible.
Requests never construct an execution client, submit/cancel orders, or reconcile. The
existing worker writes additive account observation metadata during its normal reconciliation.
No worker is started by the dashboard. Existing installations without metadata say unavailable,
including when their journal is empty. Fetch time is separate from broker observation,
last successful reconciliation, worker heartbeat and IEX trade time.

## Observation contract

`broker_observations` is exclusively live Alpaca paper account evidence. Account IDs are
broker-assigned identifiers, never API credentials. The latest attempt records `ok` only
when reconciliation reports no block. Failed/blocked attempts preserve the last successful
reconciliation and last obtained position snapshot, while marking confirmation unavailable.
A successful positions read can coexist with unresolved orders or failed reconciliation.
The view compares its scoped journal quantity with the recorded broker snapshot and shows
mismatches without repairing them. This is a last observation, not an atomic live broker view.

Thirty seconds is the bounded stale threshold: the worker ticks five seconds after each
completed tick, with bounded broker calls. Slow reconciliation can exceed thirty seconds;
that deliberately removes confirmation. Unknown, malformed and future timestamps never
establish freshness. Browser time independently expires the view even when fetches stall.
A heartbeat or fresh IEX mark never refreshes broker observation evidence.

## Protection mapping

Protection is confirmed only for a fully filled `bracket_v1` parent joined through trade ID,
entry order ID and exact live/Alpaca/account scope. There must be exactly one stop and one
target child for that parent/trade, each observed within thirty seconds, in `new`, `accepted`
or `partially_filled` state, and each broker quantity less its cumulative fill must equal
the remaining journal quantity. Account observation must be fresh and reconciliation OK.
Pending exit intent removes confirmation. Child levels shown are the journaled bracket
levels, not a new broker quote. `held` means awaiting activation, never confirmed protection;
missing/ambiguous identity, rejection, cancellation, unresolved state and insufficient quantity
remain explicit. A partial parent cannot establish protection. A closed trade has no protection
warning; its actual exit fills and booked result appear separately from IEX estimates.

Replay and unknown provenance remain visible and labeled. A `live` source alone never means
broker ownership. The selected account filters paper positions, pending entries and exit fills;
simulation/replay rows retain their own provenance. The endpoint contains no raw error text,
credentials or broker request payloads. It requires no direct broker read or credential setup.

## Verification

- Focused backend: 22 passed, including account isolation, absent metadata, partial/held/
  rejected/missing children, insufficient coverage, stale evidence, pending session close,
  zero-fill child details, closed fills and an injected telemetry-write failure.
- Full backend after review repairs: **519 passed** in 122.82s, with the existing
  LibreSSL and websockets dependency warnings.
- Frontend: **325 tests passed** across 51 files; type check, lint and production build
  passed. `git diff --check` passed.
- Chrome fixture browser check passed all nine assertions: provenance, pending held/rejected
  children, account switching, polling updates, retained data on failure, child stale expiry,
  actual completed exit, confirmed empty account and 390px mobile width. All API requests,
  including global status/server actions, were intercepted. The screenshot therefore shows
  global status unavailable intentionally. No real account was accessed.
- [Desktop fixture screenshot](evidence/issue-105-positions-fixture.png), visually inspected.
  Reproduce with an installed Puppeteer package and Chrome: start the Next development
  server, then run `POSITION_TEST_URL=http://localhost:3000/positions PUPPETEER_PATH=<package>
  node web/scripts/check-position-state.mjs`. No browser dependency was added to the app.
  Use the dev server's matching hostname; its origin guard rejects 127.0.0.1 chunk requests
  when configured for localhost.
- The pnpm launcher could not fetch/verify its pinned 10.33.0 release in the restricted
  environment. Equivalent installed binaries were used (`web/node_modules/.bin/`):
  `vitest run`, `tsc --noEmit`, `eslint`, `next build`. Dependencies/lockfiles unchanged.

## Independent review

Two fresh default-runtime agents (no custom research models) reviewed against starting
revision `4a4c801`: `standards_review` and `spec_review`, under the code-review skill.
Standards found one P2: telemetry persistence could interrupt execution. The observation
write now catches SQLite failures without changing the existing reconciliation result;
a trigger-failure regression confirms exit processing still succeeds. Reviewer confirmed resolved.
Spec found two implementation P2s: pending entries omitted child details, and child freshness
could expire before browser confirmation. Both fixed and independently re-reviewed. The third
finding requested behavioral frontend coverage; component and browser fixtures now supply it.
No material scope creep or remaining implementation findings. No new paper orders, worker
activation, strategy changes or profitability claims are part of this change.
