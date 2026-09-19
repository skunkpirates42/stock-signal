# Alpaca IEX comparison results — September 18, 2026

All 16 runs completed and were reconciled to SQLite journals and independently recomputed metrics. No strategy is promoted. RVOL alone is a candidate for additional prospective research; it has not established a stable edge.

## Data and protocol

- Eight-symbol fixed watchlist; 103,584 IEX five-minute bars, January–August 2026.
- 39 warmup sessions, 84 development sessions (March–June), 43 holdout sessions (July–August). No missing scheduled buckets in this download.
- Initial capital: $100,000 per independently restarted window and variant.
- Base costs: 2 bps round-trip spread plus 1 bp slippage per fill; adverse: 5 bps plus 2 bps per fill. No per-share fees. These are declared scenarios, not measured costs.
- Thresholds, date windows and the four variants stayed fixed. All variants saw identical input data and raw candidate populations: 31,720 development and 16,446 holdout directional candidates.
- Primary declared metric was realized net/session; the supplementary marked results below include unfinished positions and paid entry costs, without assuming liquidation fills.

## Marked results

| Window | Variant | Base net P&L | Adverse net P&L | Base marked drawdown |
|---|---|---:|---:|---:|
| development | baseline | $2,226.27 | $-10,612.79 | $3,881.57 |
| development | strength | $3,855.20 | $-5,925.97 | $4,659.70 |
| development | rvol | $-970.92 | $-9,059.47 | $5,314.65 |
| development | both | $1,490.52 | $-4,929.50 | $4,558.79 |
| holdout | baseline | $412.68 | $-5,718.88 | $3,680.91 |
| holdout | strength | $-902.36 | $-5,311.27 | $3,861.98 |
| holdout | rvol | $3,460.79 | $-105.35 | $1,789.11 |
| holdout | both | $76.77 | $-2,490.78 | $2,431.84 |

## Findings and decisions

**Baseline — retain as the research control.** Holdout closed-trade net was +$224.78 under base costs; marking five open positions raises it to +$412.68. Adverse-cost marked net is −$5,718.88. The thin base-cost result does not establish a robust strategy.

**Strength — do not promote.** Development improved over baseline, but base-cost holdout marked net fell to −$902.36 versus baseline +$412.68, with worse marked drawdown ($3,861.98 versus $3,680.91). Fewer trades alone did not help enough.

**RVOL — inconclusive; prioritize prospective research.** Holdout had 702 closed trades versus baseline 1,288. Base closed-trade net was +$3,279.37; marking four open positions raises it to +$3,460.79, with marked drawdown $1,789.11. The marked advantage over baseline was +$70.89/session, but its descriptive 95% paired block-bootstrap interval was approximately −$41.65 to +$180.88/session. Development marked net was −$970.92, and adverse holdout net was −$105.35. The stronger holdout is insufficient to establish stability. Base holdout stays positive after removing its best marked day (+$2,073.09) or its best ticker from closed-trade P&L (+$2,099.11); those are different accounting bases and descriptive checks only.

**Both — do not promote.** Base holdout marked net was only +$76.77; adverse was −$2,490.78. Combining gates reduced the benefit seen from RVOL alone.

RVOL had no missing-history rejections: it accepted 9,053/31,720 development candidates and 3,382/16,446 holdout candidates. Rejections were below-threshold participation, so the zero-trade synthetic-fixture problem is resolved. Strength rejects the first hour for individual stocks by design and exempts SPY; detailed stock/ETF and side breakdowns remain in diagnostics.json.

## Limits and next experiment

Cash dividends, short borrow fees, taxes and actual quote spreads are not modeled. The saved corporate-actions response returned 14 dividend records and no splits; its process/pay-date query does not prove exhaustive ex-date coverage. Open positions are marked to IEX closes without hypothetical exit fees. Fills remain the next completed five-minute close, not broker-realistic latency. Uncertainty uses paired five-session moving blocks, 2,000 draws and a fixed seed; intervals are descriptive and unadjusted for selecting among variants.

Keep thresholds frozen. Add complete dividend/borrow accounting and calibrate execution-cost assumptions, then collect fresh prospective baseline-versus-RVOL observations. Do not reuse this viewed holdout as an untouched test for revised rules. Define drawdown/exposure limits before considering promotion.

## Evidence

- [Base comparison](../../research-output/alpaca-iex-2026-base-v2/comparison.md) and [marked review](../../research-output/alpaca-iex-2026-base-v2/marked-review.json).
- [Adverse comparison](../../research-output/alpaca-iex-2026-adverse-v2/comparison.md) and [marked review](../../research-output/alpaca-iex-2026-adverse-v2/marked-review.json).
- [Data coverage and action review](../../research-output/alpaca-iex-2026-jan-aug/data-review.json).
- Local raw/run artifacts are gitignored; this report and the experiment protocol are retained in docs.
- 151 backend tests passed. Cached/uncached fixture results and more than 3,700 original/restarted market-data signals per scenario matched exactly. Original interrupted run directories are retained, distinct from completed `-v2` runs.
- All 16 completed runs match their saved journals, metrics and input hashes. Ending marked equities also independently reconcile to closed net plus final open-position marks minus entry costs.
