# Signal gate audit and comparison preparation — 2026-09-18

Follow-up: the Alpaca download and all 16 market-data runs are now complete. See the
[market-data results and decisions](experiments/alpaca-iex-2026-results.md). The status
and reporting gaps below describe the initial audit; a marked-equity/exposure review
and descriptive session-block uncertainty supplement were added for the completed runs.

Status: gate corrections implemented; synthetic verification only. A credible market-data comparison is pending the saved dataset. This checkout contains only `tests/fixtures/bars.json` (explicitly synthetic), and no Alpaca credentials were configured during the audit. No historical market performance or preferred variant has been established.

## Audit against the proposal

| Requirement | Finding and disposition |
|---|---|
| 12-bar stock log return minus aligned SPY return | Preserved the 60-minute endpoint calculation and fixed zero threshold; require positive finite prices and exact completed-bar endpoints. Interior missing bars are not filled; the feature measures the declared elapsed hour. |
| Entire strength interval within the current regular session | The old same-date check admitted premarket endpoints. Now enforce XNYS open, close, and five-minute alignment. |
| SPY benchmark exemption | Previously silent. Now explicitly records `not_applicable`; QQQ remains compared to SPY. |
| Prior 20 completed sessions for RVOL | The old last-20-observations rule could reach arbitrarily far back across missing sessions. Now restrict to the preceding 20 actual XNYS sessions. |
| Same session-relative bucket | Derive each reference timestamp from that session's open. Exclude buckets beyond an early close and match across daylight-saving changes. |
| At least 10 valid observations; positive median | Retained; missing/nonfinite/negative volume is unavailable, genuine zero volume remains an observation. Current session is excluded. |
| Explain decisions | Persist policy version, value, threshold, observation count, benchmark and individual reasons in `gate_json`, separately from raw direction and execution skip reason. |
| Comparable rejection distributions | Previously gates ran only when portfolio state allowed a trade. Now evaluate all directional candidates, preserving independent execution restrictions. |
| Frozen comparison | Save input file hash, metadata, windows, costs, gate version and coverage before replay. Existing per-run source/config/dataset manifests remain. Reject nonempty output directories. |
| Honest data/cost labels | Reject synthetic/unknown provenance and frictionless costs unless explicitly opted into correctness/frictionless checks. A feed label is supplied provenance, not independent verification. |
| Evaluation reporting | Add realized net/session, delta versus baseline, side and stock/ETF breakdowns, rejection counts, best-day/ticker removal and pending candidates. |

The gate input is saved completed five-minute OHLCV, with timestamps denoting bar starts. The runner cannot infer bar duration or adjustment policy from OHLCV values; verify these against the provider metadata. Default live execution remains unchanged: gates are opt-in research variants.

## Market-data run requirements

Provide JSON mapping each symbol to records with `timestamp`, `open`, `high`, `low`, `close`, and `volume`, plus an adjacent `<dataset>.meta.json` containing `feed`. Record provider, retrieval date, time interval, five-minute bar-start semantics and corporate-action adjustment policy there as well. Include SPY and the declared stock universe, keep the feed/adjustment policy fixed, and supply at least 20 prior exchange sessions for volume warmup before evaluation. Inspect missing-session/bucket coverage; do not turn missing data into zero-volume bars.

Declare chronological development and untouched holdout windows before looking at results. Window JSON uses the format in `tests/fixtures/windows.json`, with exclusive end times. Portfolios restart flat for each window; pre-window bars warm features only. Choose sufficiently long windows spanning different conditions; the fixture's one-day windows are not an evaluation design.

Example command with an **illustrative, uncalibrated** cost scenario:

```bash
SPREAD_BPS=2 SLIPPAGE_BPS=1 FEE_PER_SHARE=0 .venv/bin/python research.py \
  --dataset /path/to/bars.json --windows /path/to/windows.json \
  --output research-output/market-base
```

Repeat with a predeclared adverse-cost scenario and a fresh output directory. The fixture verification used 2 bps round-trip spread plus 1 bp slippage per fill, and 5 bps spread plus 2 bps slippage per fill. These are sensitivity assumptions, not measured execution costs or an endorsement of their realism.

Inspect `protocol.json`, `comparison.md`, `comparison.json`, and each variant's `diagnostics.json`, `manifest.json`, `trades.json` and SQLite journal. Low RVOL sample counts mean unavailable context, not evidence the filter is unprofitable. Compare all four variants without searching thresholds against the holdout. Preserve unsuccessful runs.

## Remaining evaluation limits

- Existing simulation fills at the next completed five-minute close. This is a delayed scenario, not a quote-based execution reconstruction.
- P&L and drawdown use closed trades. Overnight holdings open at the boundary are censored; missing marked-to-market equity, exposure and turnover reporting prevents a complete risk comparison. Do not rank variants on realized P&L alone when censoring differs materially.
- Session P&L is attributed to exit day and includes zero-trade exchange sessions. Best-day/ticker removal is descriptive, not a confidence interval.
- Session-block uncertainty, acceptable drawdown/exposure limits, sample adequacy, and prospective shadow-run evidence are still required before promotion. The runner explicitly produces no promotion decision.
- The dashboard does not yet expose all structured gate diagnostics. Use the saved artifacts for this audit; no frontend behavior was changed.

## Verification artifacts

Local ignored directories `research-output/gate-audit-base/` and `research-output/gate-audit-adverse/` contain four variants for each of two synthetic windows. They exercise cost accounting, reports and refusal to overwrite prior runs. Their small fixture history intentionally cannot warm RVOL; they are not trading evidence.
