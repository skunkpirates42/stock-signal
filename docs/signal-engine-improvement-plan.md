# Signal-engine improvement proposals

Status: research and implementation proposal, separate from [pipeline correctness work](implementation-plan.md). Proposed advantages are hypotheses, not established trading results.

## Recommendation

Start with benchmark-relative strength and time-of-day relative volume as independent quality gates. They add context the current votes do not contain and permit a clean comparison while preserving direction decisions. Then test whether separating trend-following from mean-reversion improves results. Add an execution-cost gate once realistic fills and cost accounting exist. Defer learned scoring until there is enough independently evaluated data.

Do not combine all ideas immediately. Each should earn its complexity in an isolated experiment before combinations are evaluated.

## What the current engine leaves unresolved

- Four of six votes clear the 62% threshold. Several inputs summarize overlapping price/trend information; six votes should not be interpreted as six independent pieces of evidence.
- Trend-following votes favor price strength, while RSI/Bollinger votes favor fading extremes. The same aggregate score can represent different economic setups.
- Volume changes displayed confidence but cannot veto execution. Its rolling 20-bar baseline also compares different times of day.
- Market regime is recorded but does not affect eligibility.
- All eligible signals receive the same sizing rule and ATR-based levels, regardless of trading friction.
- Confidence is agreement, not an estimated probability of profit. The existing README's reported gate improvements cannot be verified from this checkout.

## Idea comparison

| Idea | Advantage over current approach | Pros | Cons / failure modes | Priority |
|---|---|---|---|---|
| Benchmark-relative strength gate | Distinguishes stock-specific strength from simply following the market | Transparent; uses existing stock and SPY bars; direction rule stays unchanged | Raw relative return still contains beta effects; can remove profitable reversals; benchmark self-comparison needs a policy | First experiment |
| Time-of-day RVOL gate | Requires unusual participation rather than merely nudging the confidence label | Different information from price votes; adjusts volume baseline for session time | Needs multi-session history; sparse IEX observations; high volume can mark exhaustion | First experiment, separately |
| Regime-specific trend and reversion setups | Gives each trade a coherent setup instead of mixing incompatible votes | Clear rationale; interpretable failures; can reduce duplicate trend evidence | More branches and parameters; regime mistakes; reduced sample per setup | Second wave |
| Cost and liquidity gate | Rejects moves too small to justify execution friction | Directly targets net results; measurable with fill records | Cost estimates are uncertain; quote data adds complexity; can favor volatile riskier periods | After fill-model fixes |
| Learned trade-quality score | Estimates which rule-generated candidates are worth taking instead of treating agreement as probability | Can combine interactions and calibrate scores | High overfitting risk, correlated labels, drift, more infrastructure | Defer |

## 1. Benchmark-relative strength

Pitch: a LONG candidate should show strength beyond the broad market; a SHORT should show weakness. Keep the original vote result, then decide whether the context supports execution.

Initial experiment definition:

- Compute 12-bar log return for the stock minus the same timestamp-aligned SPY return. Use only completed regular-session bars, require the whole interval within the current session, and require valid endpoints and acceptable data freshness.
- Accept LONG when the difference is positive, SHORT when negative. Equality fails. Freeze this initial lookback and zero threshold before evaluating results.
- Exempt SPY from its own benchmark gate, explicitly recording `not_applicable`. QQQ can be compared against SPY. Report individual-stock results separately from ETF results so exemptions cannot hide gate effects.
- Missing context makes the gated variant ineligible and records why; the unchanged baseline remains available for comparison.
- If the raw-return hypothesis survives, test beta-adjusted relative strength as a separately registered experiment using past data only. Do not add it to the initial parameter search.

Implementation: add causal context features in `signals/features.py`, a pure gate in `signals/quality.py`, and an eligibility result carrying value, threshold, benchmark, decision, and reason. Persist raw signal direction separately from execution eligibility.

Evidence required: held-out net expectancy, net P&L per session, trade count, rejection distribution, and long/short results improve or reveal a useful risk tradeoff. Fewer trades with higher per-trade profit alone is insufficient.

## 2. Time-of-day relative volume

Pitch: compare this 10:00 bar with past 10:00 bars, rather than a moving average dominated by other parts of the session.

Initial experiment definition:

- RVOL = completed five-minute volume / median volume for the same session-relative five-minute bucket over the prior 20 completed sessions.
- Require at least 10 valid prior observations and a positive denominator. Exclude the current session from the reference set. Missing data is unavailable, not zero volume.
- Test a predeclared RVOL threshold of 1.5 independently from relative strength. This is a new proposed definition, not a reconstruction of the undocumented old experiment.
- Match reference buckets by exchange-session schedule; do not fabricate late-session observations on early-close days.
- Retain the original volume modifier in the baseline. Record the new gate separately so its incremental effect is measurable.

Implementation: maintain a session/bucket volume history outside the 120-bar indicator buffer; seed it from saved history and update it only after sessions complete. Version the baseline policy with each run.

Evidence required: gains survive held-out sessions and removal of the single best day/ticker. Examine whether high-RVOL trades merely increase volatility or slippage. IEX is a single exchange, so these measurements describe IEX participation rather than consolidated market volume; keep feed identity fixed across comparisons. See [Alpaca's market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).

## 3. Separate trend-following and mean-reversion setups

Pitch: stop asking the same vote tally to both follow a move and fade it.

Proposed variants:

- First, test a minimal regime-alignment gate on the existing engine: permit LONG in BULL and SHORT in BEAR; stand aside in CHOPPY or unknown context. This isolates the value of regime selection before rewriting signals.
- Next, test a trend setup using one grouped trend assessment, a pullback condition, and a completed-bar resumption trigger. A concrete starting candidate is bullish market context plus `close > SMA20 > SMA50`, a prior bar touching/breaching SMA20, and the current close recovering above it; mirror for shorts. This is a newly registered rule, not an assumed improvement.
- Separately test a reversion setup in CHOPPY context: RSI below 30 and a prior close below the lower Bollinger band, followed by a close back inside the band; mirror RSI above 70/upper band for shorts. Missing market context does not qualify as CHOPPY.
- Preserve the existing ATR exit policy during initial direction/setup comparisons. Test alternate mean-reversion targets only in a later experiment so entry and exit effects remain distinguishable.

Implementation: introduce `strategy_id` and pure strategy modules behind a small common result interface. Persist regime, setup conditions, raw candidate, and execution eligibility. Keep the original engine runnable as `consensus_v1`.

Pros: explanations describe a specific setup; failures can be attributed to trend selection, pullback timing, or reversion rather than an ambiguous score. Grouping trend evidence reduces redundant votes by design.

Cons: more rules create more opportunities to fit noise; transitions can make regime labels late. A filtered setup may produce too few independent trades to evaluate. Require adequate samples per setup and report an inconclusive result when needed.

## 4. Cost and liquidity eligibility

Pitch: a theoretically correct direction is insufficient when the planned move is small relative to spread, fees, and delayed execution.

Initial experiment definition:

- Express estimated round-trip cost per share and as a fraction of initial stop distance. Estimate it from training-period observations or a fixed declared scenario, never a candidate's future fill.
- As a first coarse experiment, require estimated round-trip cost to be at most 0.10R. Treat this threshold as a research hypothesis and evaluate nearby predeclared cost scenarios rather than optimizing many thresholds.
- Also require valid, recent prices; add quote-based spread eligibility only when historical and live quote semantics can be matched. Do not infer actual spread from OHLC alone.
- Keep position sizing fixed during this experiment. Report whether the gate concentrates trades into unusually volatile periods.

Implementation: add an execution-cost context object and eligibility reason; use the corrected simulator and stored gross/cost/net accounting. For observed Alpaca fills, do not deduct modeled spread a second time.

Advantage: directly tests the stated weak point—friction consuming a small gross edge—without adding another price-derived vote. Limitation: it cannot rescue a direction rule with negative gross expectancy, and fill-cost estimates may fail in fast markets.

## 5. Learned quality score, later

Pitch: keep transparent rule-generated candidates but learn which contexts have positive net outcomes.

Prerequisites: trustworthy execution labels, enough distinct sessions/regimes, repeatable chronological evaluation, and a stable feature schema. Do not start from the unverifiable historical headline numbers.

Proposed first model: regularized logistic regression on a small set of available-at-decision features such as relative strength, time-of-day RVOL, regime, ATR-normalized extension, and estimated cost. Fit preprocessing and calibration only within training data. Keep this optional research dependency outside the live engine initially.

Evaluate probability calibration and actual held-out net P&L. A probability of winning is not itself expected value when realized wins/losses and costs vary. Avoid converting the old agreement label into a probability or increasing size based on an unvalidated score.

Prefer the simpler rule baseline unless the learned gate delivers stable incremental value across held-out windows. This option has the highest maintenance and overfitting cost, so it is not the recommended next implementation.

## Experiment and implementation sequence

1. Complete provenance, chronological replay, execution timing, and cost-accounting work from the correctness plan. Freeze the repaired consensus baseline with a dataset manifest and configuration hash.
2. Harden indicator input semantics before new features: define handling of nonfinite values, flat-price RSI/Bollinger cases, zero volume, and insufficient history. Log ineligibility instead of allowing missing values to become accidental bearish votes. Record this baseline version change.
3. Add a pure context/eligibility interface and new storage fields for candidate direction, execution eligibility, feature values, rejection reasons, and strategy version. Update the dashboard to distinguish WAIT from a directional candidate rejected by a quality gate; leave LLM text downstream.
4. Implement relative strength and session-aware RVOL. Run four variants on identical data: baseline, strength only, RVOL only, both. Limit the initial experiment to the declared definitions.
5. Evaluate regime alignment, then the separately registered trend and reversion setups. Keep fill, size, and exit policies constant during entry comparisons.
6. Add the cost gate and test incremental effects. Only evaluate combinations supported by earlier results; retain all experiment records.
7. Shadow-run the best supported candidate alongside baseline without submitting additional orders. Compare feature parity, rejection reasons, and prospective outcomes before selecting a paper-execution configuration.

Each feature needs hand-calculated fixtures, missing/stale-input tests, and a future-perturbation test showing that changing future data cannot change earlier decisions. Feed the same saved events through replay and live-local paths to verify causal parity.

## Evaluation and promotion rules

- Split by contiguous sessions, keeping simultaneous signals across tickers in the same fold. Never random-shuffle trades across train/test.
- Use chronological training/validation windows followed by an untouched final holdout. Purge training labels whose holding periods overlap evaluation intervals. For variable-duration trades, inspect actual event intervals; a fixed row gap alone is insufficient.
- Time-ordered splitting with an optional gap is supported by [scikit-learn's TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), but this project needs session grouping and holding-period overlap handling beyond a direct row-based split.
- Predeclare the hypothesis, thresholds, cost scenarios, and comparison metric. Save unsuccessful trials as well as successful ones. Selecting among many backtests can itself produce misleading apparent performance; see [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
- Report net expectancy, net P&L per session, maximum drawdown, turnover, exposure, number of trades/sessions, and ticker/regime/side breakdowns. Use session-block uncertainty estimates rather than treating correlated trades as independent observations.
- Promote only when the candidate has positive held-out net expectancy under the declared base cost model, improves the predeclared baseline comparison, and remains acceptable under adverse-cost and concentration checks. If uncertainty is large, retain the baseline and collect more data; 50 trades alone is not proof.
- Define acceptable drawdown/exposure limits before viewing evaluation results. Do not repeatedly tune against the final holdout; a revised strategy needs a fresh prospective evaluation period.

## Deliverables

- Versioned baseline plus opt-in strategy/gate configurations.
- Causal feature and eligibility modules with meaningful regression tests.
- Saved experiment manifests and side-by-side gross/net reports.
- Dashboard explanations that show why a candidate qualified or was rejected.
- A written keep/reject/inconclusive decision for each idea, followed by a prospective shadow-run report for any promoted candidate.
