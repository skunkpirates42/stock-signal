# Alpaca IEX gate experiment — declared 2026-09-18

Completed run findings: [results and decisions](alpaca-iex-2026-results.md).

Status: prepared before downloading or inspecting market-data results. Download requires
`ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in the repository's gitignored `.env` file.
Never put credentials in the command line, tracked files, or chat.

- Universe: AAPL, NVDA, TSLA, SPY, QQQ, MSFT, AMZN, META (current fixed watchlist).
- Dataset: January 1 through August 31, 2026; UTC end September 1 exclusive.
- Warmup only: January–February; development: March–June; holdout: July–August.
- Feed: Alpaca IEX, five-minute bars, raw/unadjusted prices, XNYS regular sessions.
- Missing bars remain missing. Inspect per-symbol/session coverage before running.
- Review corporate actions: raw splits can distort indicators, returns and positions.
  Any resulting protocol change must be documented before inspecting strategy outcomes.
- Variants: unchanged consensus baseline, strength, RVOL, both; `quality_v2` definitions.
- Illustrative base costs: 2 bps round-trip spread, 1 bp slippage per fill, no fees.
- Illustrative adverse costs: 5 bps spread, 2 bps slippage per fill, no fees.
- These cost scenarios are not calibrated estimates of actual IEX execution costs.
- Primary exploratory comparison: held-out net P&L per exchange session versus baseline.
- No promotion from realized-only results: finish marked-to-market equity/exposure reporting,
  define risk limits, and assess sample uncertainty before a promotion decision.

Download using the existing Alpaca market-data SDK; no trading client or order submission:

```bash
.venv/bin/python -m data.download_history \
  --start 2026-01-01 --end 2026-09-01 \
  --output research-output/alpaca-iex-2026-jan-aug
```

The SDK follows all response pages (no total bar limit). The downloader saves `bars.json`,
`bars.meta.json` with source/settings/checksum/session coverage, and a final `COMPLETE`
marker. It refuses to replace an existing dataset directory and does not substitute
synthetic data on failure. Do not consume a directory without `COMPLETE`.

After coverage and corporate-action review, run the fixed exploratory comparisons:

```bash
SPREAD_BPS=2 SLIPPAGE_BPS=1 FEE_PER_SHARE=0 .venv/bin/python research.py \
  --dataset research-output/alpaca-iex-2026-jan-aug/bars.json \
  --windows docs/experiments/alpaca-iex-2026-windows.json \
  --output research-output/alpaca-iex-2026-base

SPREAD_BPS=5 SLIPPAGE_BPS=2 FEE_PER_SHARE=0 .venv/bin/python research.py \
  --dataset research-output/alpaca-iex-2026-jan-aug/bars.json \
  --windows docs/experiments/alpaca-iex-2026-windows.json \
  --output research-output/alpaca-iex-2026-adverse
```

Source: [Alpaca historical bars API](https://docs.alpaca.markets/us/reference/stockbars),
[SDK request definitions](https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html).
IEX observations represent one exchange, not consolidated market activity.

## Execution record

The download completed on September 18: 103,584 bars, eight symbols, 166 sessions
(39 warmup, 84 development, 43 holdout), no missing scheduled five-minute buckets.
The checksum is recorded in `bars.meta.json` and `COMPLETE`.
Alpaca's corporate-actions response is saved beside the bars. It returned 14 cash
 dividend records and no splits. The date query includes process/pay dates rather than
necessarily covering every ex-date; do not treat it as proof of complete dividend
coverage. Cash distributions and short borrow remain unmodeled.

The first `base` and `adverse` attempts were interrupted for replay performance work;
their partial SQLite journals are retained and are not completed comparisons. Finished
runs use `base-v2` and `adverse-v2`. Replay now commits journal transactions per session,
computes regime once per timestamp, and caches indicators only within one fixed dataset
and configuration. Cached/uncached fixture signals and metrics match exactly.

Before viewing market strategy outcomes, the review was extended to mark open positions
at completed bar closes, subtract paid entry costs, and report marked drawdown, observed
gross exposure and turnover. Paired candidate-minus-baseline daily P&L uncertainty uses
5-session moving blocks, 2,000 bootstrap draws and seed 20260918. Intervals are descriptive,
not adjusted for choosing among variants, and cannot establish promotion by themselves.
Run the supplement using `python -m analytics.research_review --comparison <output>`.
Marks exclude hypothetical exit fees on positions still open, dividends and short borrow.
