# Live position price display

Scope agreed with the user: add latest price, estimated unrealized P&L on remaining
shares (LONG and SHORT), distance to stop/target from the last price, and a marker
on the existing position scale. Poll while the page is visible, waiting five seconds after each request completes
to avoid overlapping requests.
Keep credentials server-side. Batch symbols and briefly cache requests. Show feed,
trade timestamp, stale/unavailable/market-closed states. Historical replay and
unknown-source records retain distances at entry. Prices are display-only and
must never affect order submission, fills, or persisted accounting.

Implementation: Next.js proxies a read-only Flask endpoint. Flask selects symbols
from currently open live positions; browser query parameters cannot select symbols
or historical sources. It batches IEX latest trades. A separate shared market-status endpoint reads the
paper clock even when there are no positions.
The cache lasts five seconds per Flask process and caches failures too. Requests
have three-second timeouts. No broker orders or journal writes are performed.

Prices older than 60 seconds are labeled stale; this is a display threshold, not a
trading rule. A missing symbol or provider failure produces unavailable prices;
a failed frontend request labels previously received prices stale. Regular-market
status comes from Alpaca's clock and is independent of last-trade freshness. The
global status area displays US regular market open/closed/unavailable on every
page, including historical views (it describes the current session). Its own
visibility-aware poll and per-process cache use 15 seconds, independent of prices
and worker health. Failed or over-60-second-old clock checks show unavailable. A
market-closed label does not claim extended-hours coverage. Estimated P&L excludes
fees and uses remaining shares, with the original share count as legacy fallback.
Prices are IEX last eligible trades, not executable bid/ask quotes or consolidated
market prices. A marker beyond stop/target is clamped to the scale; signed distances
retain the breach. The existing position-age badge is separately labeled.

Operations: use the backend's existing ALPACA_API_KEY and ALPACA_SECRET_KEY.
No browser credentials or additional configuration is required. Both the backend
and frontend need this revision. Existing page refresh keeps journal positions
up to date independently of the price polling. This change is independent of
PR #103 and its outstanding market-hours bracket acceptance.

## Verification (2026-10-28)

- Focused backend suite: 25 passed (`tests/test_position_prices.py`,
  `tests/test_dashboard.py`), offline with credentials isolated.
- Frontend suite: 319 passed; TypeScript, ESLint, production build and
  `git diff --check` passed. Installed tool binaries were used because the pnpm
  launcher could not reach the registry to verify its configured version.
- Read-only provider check at 21:05:39 UTC: clock reported closed; SPY latest IEX
  trade was 769.80 at 20:54:40.576039 UTC. No orders or account holdings were read
  or changed. This also verified Python 3.9 handling of Alpaca nanosecond input.
- Independent specification and standards reviews used separate default-runtime
  agents. Findings about serialized Server Actions and frozen freshness time were
  fixed and re-reviewed; no material findings remain. Poll timing wording was
  clarified to match the non-overlapping scheduler.
- Rendered component tests cover labels and the scale marker; no interactive
  browser visual inspection was performed. Market-open behavior is covered by
  mocked tests; the actual provider check occurred after hours.
