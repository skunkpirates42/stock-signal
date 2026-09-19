# Signal research roadmap

Written September 18, 2026. Status: planned, not implemented by this document.

## Starting point

The [completed Alpaca experiment](alpaca-iex-2026-results.md) ran all four variants with
base and adverse costs. RVOL alone had the strongest base-cost holdout, but lost money
in development and slightly under adverse holdout costs. No variant is promoted.
Marked equity, exposure, turnover and descriptive session-block intervals already exist;
reuse them rather than rebuilding them. January–August 2026 is now examined research data,
including the previously labeled holdout. Accounting corrections can be replayed on it,
but revised strategies cannot claim it as an untouched test.

## Sequence and completion gates

| Stage | Work | Completion evidence | Next decision |
|---|---|---|---|
| 1. Accounting contract | Specify dividend entitlement/accrual/payment, short distributions, borrow accrual, rounding, provenance and missing data | Reviewed specification and hand-calculated examples; explicit unavailable-data behavior | Implement only settled rules |
| 2. Accounting implementation | Add versioned cash-flow records to replay and marked equity; reconcile closed and open positions | Fixtures reconcile cash, receivables/payables, fees and equity without double counting; old artifacts preserved | Recompute historical comparisons as a correction, not new validation |
| 3. Execution-cost evidence | Audit read-only saved quotes/fills or declare bounded scenarios where observations are unavailable | Feed, timestamps, quote age, order side and cost components documented; no cost inferred from OHLC alone | Freeze a justified base/adverse model before new evaluation |
| 4. Prospective shadow system | Baseline and RVOL consume the same saved/live events with isolated hypothetical portfolios | Replay/live feature parity, restart recovery, stale-data handling, zero broker submissions | Start a registered prospective collection period |
| 5. Fixed-date review | Compare complete net/session, expectancy, marked risk, concentration and uncertainty | Reproducible report from frozen code/data/config; enough independent sessions to judge uncertainty | Paper candidate / collect more / reject |
| 6. Regime experiment | Test LONG only in BULL and SHORT only in BEAR; CHOPPY/unknown rejects | Independent comparison against the repaired consensus baseline, with causal fixtures and a new evaluation period | Keep/reject/inconclusive before any combination |
| 7. Separate setups | Independently test one trend setup and one mean-reversion setup | Explicit triggers, strategy IDs and separate reports, constant sizing/fills/exits | Combine only supported hypotheses |
| 8. Optional cost gate or learned score | Test a cost gate after cost semantics are trustworthy; learned score only after sufficient labels | New preregistration and incremental out-of-sample evidence | Defer while simpler methods remain unresolved |

Stages 1–3 can overlap only on independent artifacts: provider-data inventory and test
fixtures can proceed while the accounting contract is reviewed. Stage 4's event storage
can be built in parallel, but performance conclusions depend on corrected accounting.
Stages 6–7 do not require promoting RVOL. Test them separately against the repaired
baseline; combining filters at the outset would obscure their contributions.

## Prospective protocol to freeze before collection

Keep the eight-symbol watchlist, IEX feed, completed five-minute bars, consensus direction,
ATR exits and sizing fixed unless a separately versioned accounting correction requires
otherwise. RVOL remains current bucket volume / median of the same bucket in the previous
20 exchange sessions, at least 10 valid references, threshold 1.5, no current-session
reference. Keep baseline's volume modifier. Record all raw candidates and gate decisions.

Use the first full exchange session after shadow readiness as the prospective start;
record the actual date before ingesting that session. A proposed first review is after
60 completed sessions. This is a scheduling checkpoint, not a claim of statistical power.
Select a meaningful effect size and assess needed session count before registration;
if that requires more than 60 sessions, register the longer period. Do not repeatedly
extend collection only until a favorable result appears. Any continuation gets a dated,
separately recorded protocol before new outcomes are seen.

The registration must contain concrete values for maximum acceptable marked drawdown,
exposure, adverse-cost loss, coverage and stale-data tolerances. These are currently
**unset**; an implementing agent must not silently invent user risk preferences. Data
collection and offline engineering may proceed; promotion cannot be decided without them.

Primary metric: paired difference in fully accounted marked net P&L per exchange session.
Also report net expectancy/trade, actual trade/session counts, marked drawdown, exposure,
turnover, side/regime/ticker/ETF breakdowns, and best-day/ticker removal. Freeze uncertainty
method and handling of incomplete sessions. The existing five-session moving-block
bootstrap is a starting method to review, not proof that five sessions capture dependence.
Report absolute profitability alongside improvement over a losing baseline.

A paper candidate needs positive net expectancy under the declared base model, credible
incremental benefit, acceptable predeclared risk/adverse-cost/concentration results,
accounting reconciliation and prospective feature parity. Large uncertainty means
inconclusive; demonstrated harm means reject. Paper activation is a separate operational
change, not an automatic side effect of a report. No real-money execution is in scope.

## Work assignments

Use the [bounded task packets](tasks/README.md). Start with T01. Each task returns code or
a document plus verification evidence; it does not own unrestricted strategy research.
Use ordinary scripts for downloading, backtesting and metric calculation once implemented.
An LLM need not watch every bar or infer arithmetic from prose.

Specific assignments (reasoning effort in parentheses):

| Task | Primary model | Review model |
|---|---|---|
| T01 Accounting contract | GPT-6 Astra (high) | Separate Astra (high) + human/domain review |
| T02 Pure calculations | GPT-5.6 Luna (high) | GPT-5.6 Terra (high) |
| T03 Accounting integration | GPT-5.6 Terra (high) | GPT-6 Astra (high) |
| T04 Cost evidence | GPT-5.6 Luna (medium) | GPT-6 Astra (high) |
| T05 Shadow portfolios | GPT-5.6 Terra (high) | GPT-6 Astra (high) |
| T06 Report generation | GPT-5.6 Luna (medium) | GPT-6 Astra (high) |
| T07 Regime gate | GPT-5.6 Luna (high) | Terra (high) code review; Astra (high) experiment review |

The [task assignment table](tasks/README.md#model-assignments) records exact model IDs,
escalation rules and the official source. Automatic routing is configured; see the [delegation setup](delegation.md).
Reading this document alone starts no agents or experiments. Luna handles tightly specified components;
Terra owns shared integration; Astra owns ambiguous design and final research review.

| Work | Smaller coding model fit | Review owner |
|---|---|---|
| Artifact inventory, checksum/coverage checks, report generation | Good with explicit inputs and output schema | Automated checks, then spot review |
| Hand-calculated fixtures and pure cash-flow functions | Good after the accounting contract is settled | Independent accounting review |
| Storage fields, isolated adapters, deterministic regime gate | Good for one bounded change with tests | Integration/causality review |
| Shadow restart/order isolation and shared accounting changes | Split into small patches; avoid broad autonomous rewrite | More capable model plus human review |
| Hypotheses, leakage audit, statistical design, interpreting conflicting results | Use a more capable model | Human owns risk limits and promotion |
| Choosing trades or changing thresholds during a run | Not an LLM responsibility | Frozen deterministic code |

This is a project-specific delegation recommendation, not a guarantee that a particular
model succeeds. Trial a smaller model on T02 using the same packet and verification rubric
as a stronger model. Compare correctness, unplanned edits, retries, wall time and total
cost including review. Escalate when it cannot explain a reconciliation discrepancy,
needs to change the contract, or fails meaningful checks after a focused repair attempt.
Do not use model size as evidence of trading validity.

Official OpenAI guidance recommends establishing task-specific evaluations and iterating
against measurable quality; use that principle to qualify a cheaper model for these
packets rather than assuming competence from its name:
[Model optimization](https://developers.openai.com/api/docs/guides/model-optimization).
No particular subscription, current model availability or price is assumed here.
