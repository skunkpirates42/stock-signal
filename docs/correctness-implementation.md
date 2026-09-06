# Correctness implementation record

Implemented on `fix/pipeline-correctness`.

| Plan area | Implementation |
|---|---|
| Configuration and initialization | Root `.env` loading before settings, environment precedence, setting validation, fresh API/report database initialization, additive schema journal |
| Provenance | Source/backend/account-scoped restoration, separate default replay DB, run IDs and manifests, explicit legacy mapping with evidence |
| Broker state | Durable client order IDs, confirmed cumulative fills, partial exposure/P&L, restart lookup, drift blocking, bounded SDK requests, one worker outside ingestion |
| Replay | Timestamp batches, exits before deterministic allocation, exposure cap, causal regime context, every eligible signal logged, historical fill timestamps |
| Fill/session policy | Shared delayed local fills, gross/cost/net accounting, separate trigger/outcome, XNYS boundaries, final-bucket clock flushing, incomplete/duplicate handling, optional flatten policy |
| Research | Saved datasets and checksums, code/config fingerprints, fixed baseline/strength/RVOL/both comparisons on declared development/holdout windows, fixture metrics |
| Dashboard | Scoped open positions and labels, historical fill times, recorded-net cost basis, breakeven outcomes, visibility-aware refresh, worker/data status and unresolved orders |

## Deliberate choices and limits

- Local simulation fills at the **next completed five-minute observation's close**.
  This is a conservative five-minute delay model. It is not the earliest executable quote
  and is not equivalent to Alpaca's market-order latency. Replay and local live use the
  same policy, with a regression comparing minute aggregation to portfolio replay.
- Overnight holding remains default. Flattening is attempted before the scheduled close;
  missing data or unconfirmed execution preserves exposure. No fill is invented at the
  market's closing boundary.
- Broker submission timeouts remain unresolved until lookup succeeds. An unknown request
  is never automatically resubmitted with a new ID. Restarts adopt confirmed cumulative
  quantities transactionally and do not replay already-applied P&L.
- The pinned calendar is compatible with the existing Python/pandas versions. Exceptional
  future closures need calendar maintenance. The Alpaca SDK timeout hook is isolated and
  tested because the installed SDK does not expose a public per-request timeout setting.
- Legacy records keep their original outcome/P&L. Unknown scope remains unknown and blocks
  automatic adoption. New outcomes derive from realized P&L, independently of trigger.
- Baseline/strength/RVOL/both are opt-in research variants, not changes to default live
  eligibility. Their definitions are new and cannot recreate missing historical inputs.
- Existing README performance claims are explicitly archived and unverified. The saved
  fixture is synthetic and its metrics are correctness checks, not trading evidence.

## Verification

- Backend suite: 119 tests, including migration, configuration imports from another CWD,
  lost broker responses, partial fills, restart idempotence, exposure drift, SDK timeout
  contract, source isolation, sessions/DST/early closes, invalid indicators, cost accounting,
  chronological replay, causality, live/replay parity, and fixture-to-Flask results.
- Frontend suite: 105 tests, including visibility-aware polling and stale-heartbeat state.
- TypeScript, ESLint, and Next.js production build passed.
- All three built Next.js routes rendered against the synthetic fixture API. Verified
  Overview's recorded-net label/result and Positions/Signals fixture contents.
- The research command completed all four variants across the committed development and
  holdout windows. Small fixture history intentionally leaves RVOL under-warmed.
- Syntax compilation and whitespace validation passed.

No credentials were used to fetch market data or submit orders. The connected paper-account
smoke test remains an explicit operational step in [paper-smoke-test.md](paper-smoke-test.md).
