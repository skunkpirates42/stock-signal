# Issue 99 step 4: Alpaca bracket execution

Base: merged PR #102, `32e30e6`. Issues #97 and #99. Worker error handling from
PR #101 is already merged. Local execution and frozen research policies are unchanged.

## Policy

New Alpaca paper entries use `bracket_v1`, recorded in each durable entry payload:
market parent, take-profit limit, stop-loss stop (no stop-limit cap), GTC so overnight
positions retain protection. Prices round half-up to broker precision (two decimals
at $1 or above, four below); reject levels that collapse across the signal entry.
The broker may reject levels relative to its current market; no automatic resubmission
or theoretical fill substitutes for confirmation. Legacy simple orders retain their
existing reconciliation and bar-triggered exit behavior.

Children are durable exit orders linked by parent identity and trade ID. Worker ticks
reconcile them without waiting for a five-minute bar. Only confirmed cumulative fills
change exposure or P&L; repeated observations and restarts apply each fill once.
Resting protective orders do not globally block new entries. Uncertain execution,
missing protection, quantity mismatch and double fills block new entries. Partially
filled parents remain blocked: Alpaca activates protection only after a complete fill.

Session flatten saves its intent, cancels the bracket, and waits for observed terminal
states before submitting a market exit for remaining shares. A cancellation response
alone is insufficient. Missing child identities prevent flatten from racing unknown
orders. Pending flatten survives restart even if the session policy later changes.

Alpaca fills can slip through stops and its two exit orders can race; OHLC stop-first
and exact next-open simulation cannot be enforced at the broker. Broker fill prices and
timestamps remain authoritative. See [Alpaca order documentation](https://docs.alpaca.markets/us/docs/orders-at-alpaca)
for child activation, cancellation, GTC and partial-quantity semantics.

## Fixture comparison

| Metric | Previous step | Brackets |
|---|---:|---:|
| Closed / open | 28 / 2 | 28 / 2 |
| Win rate | 53.6% (15W / 13L) | 53.6% (15W / 13L) |
| Average win / loss | +111.87 / -72.71 | +111.87 / -72.71 |
| Expectancy | +26.17 | +26.17 |
| Profit factor | 1.775 | 1.775 |
| Total P&L | +732.78 | +732.78 |
| Maximum drawdown | 314.29 (0.311%) | 314.29 (0.311%) |
| Average bars held | 9.3 | 9.3 |
| Realized R / win R / loss R | +0.607 / +2 / -1 | +0.607 / +2 / -1 |

No metric moves because replay uses local execution. The expected snapshot and replay
fill/exit policy labels remain unchanged. Run artifacts:
`/tmp/stock-signal-97-bracket-after.db` and `/tmp/stock-signal-97-bracket-after-report`.

## Acceptance status

Offline fake-client coverage includes both directions, stop and target confirmed fills,
gap/slippage prices, child discovery, lost entry responses, restart idempotency, partial
entry, partial target followed by resized stop, cancellation acknowledgement versus
confirmation, fills racing cancellation, double-fill exposure mismatch, and heartbeat
reconciliation with no market bars. Existing simple-order recovery tests use an explicit
legacy fixture. Full-suite results and independent review follow below.

Market hours ended while this change was being implemented (2026-10-28, after 16:00 EDT).
No broker orders were submitted, no configuration was activated and no collector is left
running. A fresh bounded market-hours acceptance remains pending; keep the PR draft and
#97 open until that evidence is available.
