# Live position price display

Scope agreed with the user: add latest price, estimated unrealized P&L on remaining
shares (LONG and SHORT), distance to stop/target from the last price, and a marker
on the existing position scale. Poll every five seconds while the page is visible.
Keep credentials server-side. Batch symbols and briefly cache requests. Show feed,
trade timestamp, stale/unavailable/market-closed states. Historical replay and
unknown-source records retain distances at entry. Prices are display-only and
must never affect order submission, fills, or persisted accounting.

Implementation: Next.js proxies a read-only Flask endpoint. Flask selects symbols
from currently open live positions; browser query parameters cannot select symbols
or historical sources. It batches IEX latest trades and reads the paper clock.
The cache lasts five seconds per Flask process and caches failures too. Requests
have three-second timeouts. No broker orders or journal writes are performed.

Prices older than 60 seconds are labeled stale; this is a display threshold, not a
trading rule. A missing symbol or provider failure produces unavailable prices;
a failed frontend request labels previously received prices stale. Regular-market
status comes from Alpaca's clock and is independent of last-trade freshness. A
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
