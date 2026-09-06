# Trading pipeline correctness and research reproducibility

Status: implemented on `fix/pipeline-correctness`. See [implementation record](correctness-implementation.md) for verification, execution-policy choices, and the opt-in connected smoke test.

## Objective

Fix the six findings from the codebase investigation, plus dashboard freshness: preserve confirmed broker state, isolate execution histories, replay portfolios chronologically, model executable fills and sessions, make research reproducible, and load configuration consistently.

Baseline validation: 92 Python tests and 103 Vitest tests passed during investigation. These tests currently include an assertion that an unsuccessful Alpaca close should be recorded at a theoretical price; that assertion must be replaced.

## Decisions and scope

- Retain the six-vote signal rules and presentation-only LLM synthesis.
- Keep Alpaca execution paper-only. Do not add real-money execution.
- Preserve original records through additive, versioned migrations. Unknown historical provenance stays unknown; do not infer it from arbitrary row-ID cutoffs.
- Separate signal decisions, execution status, exit triggers, and realized outcomes. A target trigger does not guarantee profitable execution.
- Retain bar-driven exits as the default execution policy. Model their delay explicitly; do not describe them as resting stop or limit orders.
- Preserve overnight holding as an explicit default for compatibility. Add an optional session-close policy and label results by policy; do not silently change strategy behavior.
- Defer strategy-quality claims until a reproducible experiment exists. New gates remain opt-in research features.

## 1. Consistent configuration and database initialization

Files: `config.py`, all Python runners, `scripts/`, `.env.example`, `dashboard/app.py`.

Implementation:

- Load the repository-root `.env` once before reading environment-backed settings. Explicit process environment values take precedence, independent of working directory.
- Validate broker/provider names, numeric bounds, and required credentials for explicitly selected network modes. Keep implicit synthetic selection limited to absent credentials; provider failures must remain visible.
- Initialize the schema before dashboard/report queries so an empty installation returns empty results rather than missing-table errors.
- Replace catch-all migration error suppression with versioned migrations and explicit schema checks. Surface unexpected migration failures.
- Document supported variables; remove or mark unused example variables such as `DATABASE_URL` and Telegram settings. Keep the paper endpoint guarantee clear.

Acceptance:

- Subprocess tests cover every runner's configuration bootstrap from a different working directory, `.env` values, environment overrides, and invalid values without network calls.
- A fresh database serves empty dashboard metrics and positions. Repeated initialization preserves data.
- Migration tests cover the current complete schema and representative legacy schemas.

## 2. Provenance and execution-scope isolation

Files: `db/logger.py`, `live/trader.py`, `backtest.py`, `analytics/metrics.py`, `dashboard/app.py`, `web/src/lib/api.ts`, positions/signals/overview pages.

Implementation:

- Add explicit scope parameters to open-position, realized-P&L, trade, and alert queries. Live restoration must require `source=live`.
- Record execution backend and an account namespace without secrets. Local-live and Alpaca-paper positions must not be restored into one another. Broker switches with ambiguous legacy open positions require reconciliation, not automatic adoption.
- Add run metadata for research: run ID, source, backend, configuration snapshot, code revision, feed, data interval, and fill/session policy. Relate new signals/trades to the run.
- Prefer a separate default backtest database, while preserving explicit `DB_PATH` overrides and enforcing scope even in mixed databases.
- Define dashboard behavior consistently: live positions by default; an all-source view labels any replay positions explicitly. Apply the same scope to counts, tables, alerts, and P&L.
- Keep untagged historical rows visible in a clearly labeled historical view, excluded from automatic live restoration.

Acceptance:

- Fixtures containing live-local, live-Alpaca, replay, and unknown rows prove that restarts restore only the intended scope.
- Live and replay positions in the same ticker cannot overwrite one another during restoration.
- API and UI tests verify that source labels and returned positions agree, including empty live datasets.

## 3. Durable order lifecycle and broker reconciliation

Files: `trades/alpaca_broker.py`, `live/trader.py`, `db/logger.py`, `tests/test_alpaca_broker.py`, `tests/test_live.py`; new order persistence module as needed.

Implementation:

- Persist order intent before submission, with a stable client order ID and states for pending submission, accepted, partial fill, filled, canceled, rejected, and unresolved. Track requested quantity, cumulative filled quantity, confirmed average fill, broker ID, and last error.
- Submit entries and exits idempotently. After a timeout or interrupted request, query the existing order before retrying; a timeout is not evidence that no order exists.
- Never remove a position or close its trade until execution is confirmed. Remove the theoretical-price exception fallback. Missing fill data remains unresolved.
- Preserve partial fills and remaining exposure. Update cumulative execution facts and realized P&L transactionally without counting fills twice; finalize the trade only after remaining exposure is zero.
- Separate `exit_reason` from outcome. Derive WIN/LOSS/BREAKEVEN from realized net P&L, and update analytics/API types accordingly. Do not relabel historical trades without an explicit migration policy.
- Reconcile at startup and after uncertain execution using orders, position direction/quantity, and account identity. Failed reconciliation reads must not become an empty position set.
- Pause new orders for unresolved exposure while continuing reconciliation and management of known positions. Surface the reason through logs and dashboard status.
- Replace synchronous fill polling in the websocket callback with an order-processing path that cannot stall market-data ingestion. Serialize broker mutations and database updates.

Acceptance:

- Replace `test_close_falls_back_to_theoretical_on_error` with tests proving failed, rejected, timed-out, and partial exits preserve remaining exposure.
- Fault-injection tests cover crashes before submission, after broker acceptance but before DB acknowledgment, and after fills but before bookkeeping completion.
- Restart/retry tests prove no duplicate order submission or duplicate realized P&L.
- A delayed broker response does not prevent another ticker's bar from being ingested.
- A profitable trigger followed by a losing fill produces a loss, retaining its original exit reason.

## 4. Chronological portfolio replay and historical timestamps

Files: `backtest.py`, `data/alpaca_rest.py`, `data/sample_data.py`, `db/logger.py`, `analytics/metrics.py`; new replay tests.

Implementation:

- Replace ticker-at-a-time replay with a global timestamp-ordered event loop. Normalize UTC timestamps, deduplicate bars, validate ordering, and handle unequal histories explicitly.
- For each timestamp, update available symbol windows, resolve prior pending execution/exits, then evaluate new signals with a documented deterministic allocation order.
- Compute regime context only from SPY/QQQ bars available at or before the decision timestamp, with a defined freshness bound. Missing/stale context is unknown, not silently aligned by row index.
- Log every eligible signal, including WAIT and signals observed while already holding a position. Record whether execution was skipped and why.
- Store signal bar time, decision time, entry fill time, and exit fill time separately from insertion/audit timestamps. Build replay equity curves from historical fill order.
- Track allocated exposure and available buying power; do not reuse the full capital balance independently for simultaneous positions. Persist the allocation rule in run metadata.
- Keep open positions at dataset end explicitly censored unless the selected policy closes them at an executable final event.

Acceptance:

- Shuffling input ticker order produces identical trades, sizing, and equity under the fixed allocation policy.
- Missing SPY/QQQ bars cannot introduce future context. Unequal ticker histories produce correct timestamp alignment.
- Hand-calculated multi-ticker fixtures verify capital, overlapping exposure, and historical equity order.
- Re-running the same saved dataset and configuration produces the same results in a new run.

## 5. Execution realism and session lifecycle

Files: `trades/executor.py`, `trades/tracker.py`, `live/trader.py`, `data/alpaca_stream.py`, data adapters, analytics and cost UI.

Implementation:

- Introduce an explicit fill-policy interface shared by local live simulation and replay. Queue entry after a completed-bar decision and fill on the next available executable event, not the already-observed close.
- For the default bar-driven exit policy, detect the trigger on the completed bar and model the following executable market fill. Retain conservative stop-first labeling when both thresholds were touched.
- Keep any optional intrabar resting-order approximation a separately named research policy. Model opening gaps correctly and never compare its results as equivalent to the live bar-driven policy.
- Configure adverse spread/slippage and fees with documented units. Persist gross P&L, costs, and net P&L separately. Clearly distinguish modeled costs from broker-observed execution prices; avoid charging modeled spread twice on real fills.
- Replace weekday/time-only session assumptions with exchange-session boundaries, including holidays and early closes. Resolve the calendar provider and its documented API during implementation.
- Add clock-driven bucket finalization after a defined lateness allowance so the final bucket closes without waiting for tomorrow's first bar. Deduplicate seed/live overlap and late bars; incomplete/stale data must not create fabricated bars or fills.
- Implement explicit overnight and optional flatten-before-close policies. Submit flatten orders before the session ends, reconcile failures, and retain unresolved exposure rather than manufacturing a closing fill.
- Define holding duration as elapsed time plus observed trading-bar count; persist both so restarts and overnight gaps do not inflate bars held.
- Update the dashboard cost control to show an additional hypothetical cost adjustment only when appropriate, with the stored net/gross basis labeled.

Acceptance:

- Fixtures cover next-event entry, long/short gaps, both thresholds touched, missing next bars, and cost-adjusted P&L.
- Clock tests cover 15:55 finalization, early close, DST boundaries, holidays, missing minutes, late/duplicate bars, and REST/live overlap.
- Live-local and replay consume the same controlled event sequence and produce the same decisions and fills under identical policies.
- Both overnight and flatten policies have restart/failure tests; neither silently erases exposure.

## 6. Reproducible research and documentation

Files: `README.md`, `CLAUDE.md`, `backtest.py`, new research runner/artifact format, optional `signals/quality.py`.

Implementation:

- Immediately label the existing numeric findings as historical, unverified results whose dataset/configuration are unavailable. Remove assertions that the checked-in engine already implements the reported gates or establishes a validated edge.
- Add explicit dataset start/end, feed, symbol list, saved-bar checksum, configuration, code revision, and command manifest to each research run. Keep credentials and licensed datasets out of tracked artifacts as appropriate.
- Export machine-readable trades, metrics, and run manifest plus a human-readable report. Use small deterministic fixtures for checked-in reproducibility tests.
- Define optional relative-strength and RVOL gates precisely before implementation: benchmark, return lookback, direction-specific test, volume baseline, minimum history, and missing-data policy. The original formulas cannot be recovered from the current README; any newly chosen definitions are new experiments.
- Compare baseline, relative strength, RVOL, and both gates on the same dataset, fill model, and split. Log gate inputs and rejection reasons without changing the six-vote direction decision.
- Separate development/tuning periods from held-out evaluation and walk-forward windows. Report gross/net results, drawdown, sample sizes, and ticker/regime breakdowns for each window, including unsuccessful configurations.
- Update outdated architecture descriptions and startup commands to match implemented behavior.

Acceptance:

- A documented command reproduces a committed fixture report with no network access.
- Causality tests prove future bar changes cannot alter earlier gate decisions.
- Reports identify datasets, policies, and configurations uniquely and never present synthetic results as observed market performance.
- No claim depends on reproducing the old 2,464-trade result without its missing inputs.

## 7. Dashboard freshness and operational visibility

Files: `dashboard/app.py`, `web/src/app/`, `web/src/components/`, `web/src/lib/`.

Implementation:

- Add a modest polling refresh while the page is visible, clean up timers, and preserve filters and explanation interaction state. Read the installed Next.js guides required by `web/AGENTS.md` before implementing framework changes.
- Expose latest data timestamp, selected execution scope, connection/ingestion status, and unresolved orders. Distinguish a successfully refreshed dashboard from a healthy trading stream.
- Show gross/net metric basis and stale-position context accurately. Keep current-quote distances absent unless a quote feed is actually implemented.
- Keep the legacy dashboard operational or explicitly document its status; adding full browser-alert parity to Next.js is a separate enhancement.

Acceptance:

- Integration tests verify newly logged data appears after refresh, hidden tabs stop polling, filters remain selected, and errors show stale data honestly.
- An unresolved exit appears as remaining exposure rather than a closed winner.

## Delivery sequence and release checks

Implement as reviewable changes in the order above. Phases 1–3 establish configuration, provenance, and durable state. Phases 4–5 establish trustworthy simulation semantics. Phase 6 experiments depend on those semantics; its correction of unsupported documentation can happen immediately. Phase 7 completes the user-facing presentation of the new states.

For each phase, run targeted regressions and the existing backend/frontend suites affected by the change. Run TypeScript checking and lint for frontend changes, and a production build once the dashboard integration is complete. Test migrations against copies of legacy databases before any operational migration.

Final acceptance requires an offline end-to-end fixture spanning bars → signals → execution → SQLite → Flask → dashboard, crash/restart tests with a fake broker, and a documented opt-in Alpaca paper smoke test. The smoke test must verify confirmed fills and recovery behavior; profitability is not a correctness criterion. Existing historical performance numbers must be recomputed under the new semantics before comparison or publication.
