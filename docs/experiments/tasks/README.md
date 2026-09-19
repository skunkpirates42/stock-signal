# Bounded experiment tasks for coding agents

Status: all tasks below are planned. Implement one packet per assignment. This document
does not start agents, authorize paid services, or activate trading. See the
[roadmap](../roadmap.md) for dependencies and the [existing findings](../alpaca-iex-2026-results.md).

## Model assignments

Assigned September 18, 2026. These are project recommendations, not measured task-specific
benchmarks. Reasoning settings are starting configurations, not guarantees of correctness.
The current session exposes all three model IDs below; availability in another session or
account should be checked rather than silently substituting a different model.

| Task | Primary model | Reasoning | Reviewer |
|---|---|---|---|
| T01 Accounting contract | GPT-6 Astra | high | Separate Astra high review + human/domain review |
| T02 Pure cash-flow calculations | GPT-5.6 Luna | high | Terra high |
| T03 Accounting integration | GPT-5.6 Terra | high | Astra high |
| T04 Cost evidence inventory | GPT-5.6 Luna | medium | Astra high |
| T05 Shadow portfolios | GPT-5.6 Terra | high | Astra high |
| T06 Reports | GPT-5.6 Luna | medium | Astra high for statistics/decision |
| T07 Regime gate | GPT-5.6 Luna | high | Terra high for code; Astra high for experiment |

Exact IDs: `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-6-astra`. Use a separate review pass that
receives the contract, patch and test evidence and independently checks them. Review by
the same model family is not independent empirical validation of a trading strategy.

Escalate Luna to Terra (`high`) for unresolved implementation failures after one focused
repair attempt. Escalate Terra to Astra (`high`) for cross-module or reconciliation issues.
Unsettled accounting rules, data leakage, statistical design and promotion conclusions go
directly to Astra plus the required human judgment. Missing data/credentials or unset user
risk limits remain dependencies; a bigger model cannot resolve them by guessing.

OpenAI describes Astra as suited to complex reasoning/coding, Terra as balancing capability
and cost, and Luna as aimed at cost-sensitive workloads. The assignments above apply that
broad guidance to this repo; qualify them using the packet's tests and review rubric.
Source: [official model catalog](https://developers.openai.com/api/docs/models).
Automatic routing is now configured in root `AGENTS.md` and `.codex/agents/`; see the
[delegation setup](../delegation.md). Requesting task execution triggers delegation when
the runtime supports it; reading this document alone does not start tasks or change the
coordinating session's model.

## Common handoff contract

Read `CLAUDE.md`, the roadmap, the assigned packet and the named implementation files.
Inspect existing tests before editing. Do not reset or overwrite the current working tree;
there are existing research changes. Preserve old results and use new output directories.
Check whether the named paths exist; proposed files are marked as proposed.

Keep voting rules, RVOL threshold, sizing and execution policy unchanged unless the packet
explicitly owns that change. Keep LLM text downstream of all trade decisions. Never use
examined historical data as fresh validation or optimize thresholds against July–August.

Offline tests must not load real credentials or submit orders. Retain `tests/conftest.py`
isolation; use dummy credentials in fake-client tests. Do not print `.env`, environment
values, request headers or verbose HTTP exception locals. Any authenticated data fetch
must use the existing read-only adapter and applicable network permission controls.

Return: files changed, assumptions, exact checks and outcomes, sample artifact, known gaps,
and whether acceptance is met. Distinguish implementation correctness from profitability.
If required data or semantics are missing, complete independent work and identify the
specific dependency; do not fabricate fills, rates, dividends or evaluation results.

Use `.venv/bin/python -m pytest <relevant-test-files> -q --tb=short` and `git diff --check`.
Run the complete backend suite for shared accounting, storage or replay changes. No
frontend changes are needed in these packets. Documentation-only tasks need link/content
checks, not runtime tests.

## T01 — Accounting contract

**Owner:** GPT-6 Astra (`gpt-6-astra`), reasoning `high`.
**Review:** separate GPT-6 Astra (`high`) review of the contract and examples; human/domain
review resolves uncertain broker semantics. **Depends on:** none. **Output:** proposed `docs/experiments/accounting-contract.md`.

Read `trades/executor.py`, `db/logger.py`, `backtest.py`, `analytics/research_review.py`,
`data/review_history.py` and the saved corporate-actions response. Specify, before code:

- Stable action identifiers, effective/ex-date, entitlement cutoff, payable date, revision
  provenance, and how completeness is established independently of process-date queries.
- Long receivables and short distribution liabilities: distinguish economic accrual from
  cash settlement and prevent counting the same benefit/cost twice in marked equity.
- Position ownership across entry, exit, ex-date, payment and window boundaries. Include
  holdings closed after entitlement but before payment. State exceptional-action handling.
- Borrow eligibility and cost: source of historical availability/rates, rate timestamp,
  accrual base, day-count convention, weekends and missing-rate policy. A modeled rate is
  a labeled scenario; lack of data is not free borrowing or guaranteed short availability.
- How accruing costs affect available capital and sizing; separate accounting-only
  restatements from reruns where corrected capital changes subsequent trades.
- Rounding, taxes excluded if applicable, corrections/idempotency, reconciliation identity
  and the version change needed for artifacts and schema.

**Accept:** hand-worked long dividend, short dividend, pre-ex-date close, entry on ex-date,
close-before-pay-date, borrow over a weekend, missing rate, and duplicate/corrected action
examples. Every uncertain convention is explicit. Do not implement or guess unspecified
financial rules; verify provider-specific semantics from primary documentation.

## T02 — Implement cash-flow fixtures and pure calculations

**Owner:** GPT-5.6 Luna (`gpt-5.6-luna`), reasoning `high`, after T01 is settled.
**Review:** GPT-5.6 Terra (`gpt-5.6-terra`), reasoning `high`, checks fixtures and identities. **Depends on:** T01.
**Scope:** proposed `trades/cashflows.py`, `tests/test_cashflows.py`, synthetic fixtures.

Implement the contract's pure calculation functions and typed/plain-data result interface.
Use explicit inputs for holdings, actions, rates and time boundaries. No network, SQLite,
model calls, broker calls or changes to entry/exit decisions in this packet.

**Accept:** independently hand-calculated fixtures from T01, both sides, unknown inputs,
rounding, zero positions, duplicate action IDs and time-boundary cases. Perturb records
not available at the decision time and show earlier decisions/features are unchanged.
Distinguish eventual realized accounting updates from information available to the strategy.
Smaller-model trial: pass fixtures without weakening assertions, stay within scope, explain
at least one long/short sign and one accrual/settlement identity.

## T03 — Integrate versioned accounting and reconcile historical runs

**Owner:** GPT-5.6 Terra (`gpt-5.6-terra`), reasoning `high`, in bounded patches.
**Review:** GPT-6 Astra (`gpt-6-astra`), reasoning `high`, for accounting integration and replay.
**Depends on:** T01–T02. **Scope:** `db/logger.py`, `trades/executor.py`, `backtest.py`,
`analytics/research_review.py`; proposed accounting integration tests.

Add additive cash-flow storage with run/account/source provenance and stable deduplication.
Integrate accrual/settlement into the agreed equity and capital policies. Preserve old
SQLite records and result directories. Replay corrected base/adverse variants as a new
accounting version; label them historical corrections on already examined data.

**Accept:** no duplicated distributions/costs after restart/replay, correct long/short
signs, open-position and post-close entitlements, cash/equity reconciliation, identical
results when the new policy has no applicable cash flows, and explicit unavailable-data
counts. Full backend suite passes. If historical rates/actions are unavailable, ship
fixtures and labeled scenarios; do not call the historical accounting complete.

## T04 — Cost evidence and frozen assumptions

**Owner:** GPT-5.6 Luna (`gpt-5.6-luna`), reasoning `medium`, for inventory/reporting.
**Review:** GPT-6 Astra (`gpt-6-astra`), reasoning `high`, for assumptions and interpretation.
**Depends on:** can inventory now; finalized assumptions require T01.
**Scope:** proposed `docs/experiments/cost-evidence.md` and a focused offline analysis script.

Inventory saved quotes and observed fills without submitting orders. If absent, identify
an authorized read-only source or document the gap. Define spread, slippage, commissions,
borrow and dividend treatment separately. Match quote/fill timestamps, side, feed and age;
never estimate actual spread from OHLC or deduct modeled spread again from observed fills.
Do not treat paper fills as proof of real execution quality.

**Accept:** reproducible source/coverage table, stale/missing observations excluded with
reasons, base/adverse assumptions with provenance or explicit scenario labels, and no
future quote/fill used to decide past eligibility. No threshold sweep. Hand off unresolved
cost uncertainty rather than silently choosing flattering values.

## T05 — Shadow baseline versus RVOL

**Owner:** GPT-5.6 Terra (`gpt-5.6-terra`), reasoning `high`, for shadow integration.
**Review:** GPT-6 Astra (`gpt-6-astra`), reasoning `high`, for order isolation, causality and
restart behavior. Optional isolated fixture work can use GPT-5.6 Luna (`high`). **Depends on:** T03–T04 for evaluable results;
event capture/fixtures may be built earlier.
**Scope:** proposed `research/shadow.py` and tests; reuse `live/trader.py`,
`signals/quality.py`, session helpers and current journal contracts.

Fan out identical immutable completed-bar events to two isolated local portfolios. Build
session/bucket history from prior completed sessions, not only the 120-bar indicator buffer.
The existing saved-data ResearchGate is not automatically a live history service; implement
and test history initialization, completed-session updates and feed identity explicitly.
Persist raw candidates, eligibility, gate values/reasons, hypothetical positions, marks,
costs and code/config/data identities. Include an offline replay entry point.

**Accept:** an order-submission spy fails immediately if called; changing `BROKER=alpaca`
does not instantiate a trading client in shadow mode; no paid LLM calls. Replay/live
features match on identical events. Test stale/missing data, insufficient history, early
close/DST, duplicates, future perturbations, crash/restart and isolated portfolio cash.
Do not start an unattended collector or change live execution defaults as a coding side
effect. Register dates/review schedule and identify the intended operator before operation.

## T06 — Registered review and keep/reject/inconclusive report

**Owner:** GPT-5.6 Luna (`gpt-5.6-luna`), reasoning `medium`, for deterministic reports.
**Review:** GPT-6 Astra (`gpt-6-astra`), reasoning `high`, for statistics and the decision memo. **Depends on:** T03–T05 and the registered collection period.
**Scope:** `research.py`, `analytics/research_review.py`, proposed dated report/protocol files.

Implement a report command that verifies immutable manifests and reconciles journals before
summarizing fully accounted marked net/session, net expectancy, risk, exposure, turnover,
concentration, subgroups and paired uncertainty. Include excluded/incomplete sessions and
absolute profitability. Require matching candidate populations/feed/calendar policies.
Keep all trials, including rejected ones. Do not automatically extend the horizon or tune
thresholds after inspecting performance.

**Accept:** known-answer fixture report, deliberate checksum mismatch rejection, consistent
accounting basis for day/ticker removal, frozen uncertainty settings, no double-counted
costs, and a written decision justified by the predeclared criteria. Unset risk limits or
insufficient samples mean no promotion; data collection is not blocked by that alone.

## T07 — Minimal regime gate

**Owner:** GPT-5.6 Luna (`gpt-5.6-luna`), reasoning `high`, once the protocol is frozen.
**Review:** GPT-5.6 Terra (`gpt-5.6-terra`), reasoning `high`, for implementation;
GPT-6 Astra (`gpt-6-astra`, `high`) for experiment design and conclusions.
**Depends on:** trustworthy accounting/cost policy; independent of RVOL promotion.
**Scope:** `signals/regime.py`, `signals/quality.py`, runner configuration and new fixtures.

Preserve the consensus direction. Permit LONG only in BULL and SHORT only in BEAR; reject
CHOPPY and unknown/stale context. Do not combine with RVOL in the first experiment. Existing
`classify(None)` returns CHOPPY, so preserve unknownness explicitly in the gate's context
contract. Keep sizing, fills and ATR exits identical across variants.

**Accept:** a truth-table test across all directions/regimes, stale/missing SPY cases,
causal replay parity and persisted reasons. Register a separate evaluation period before
viewing results. Report opportunity loss and net/session, not just win rate.

## Later packets — not ready for implementation

Separate trend and reversion setups need exact, unambiguous trigger definitions and
strategy-version contracts before assignment. A cost gate needs validated cost context.
Learned scoring needs sufficient independently evaluated labels and a chronological
training/calibration/evaluation design. GPT-6 Astra (`high`) should draft these packets when
the prerequisites exist; assign implementation models once their scope is defined.

## Copyable assignment

> Use GPT-5.6 Luna (`gpt-5.6-luna`) with reasoning `high`.
> Implement task T02 from docs/experiments/tasks/README.md only, using the settled T01
> accounting contract. Follow the common handoff contract. First verify the dependency
> exists and is explicit enough to implement. Do not change strategy thresholds or live
> execution. Use synthetic fixtures and no credentials. Return the patch, exact checks,
> a hand-calculated example, remaining gaps and acceptance status. If T01 is unresolved,
> implement only unambiguous independent fixtures and identify the missing convention.

Route the completed T02 patch to GPT-5.6 Terra (`high`) for the specified review.
