# T04 cost evidence inventory and frozen scenarios

Prepared 2026-09-19 from the saved `research-output/` tree by
[`scripts/cost_evidence.py`](../../scripts/cost_evidence.py). This is an offline
inventory. It does not access the broker, submit orders, start a collector, or
establish profitability. The T01 accounting contract remains proposed, so the
scenario labels below are suitable for reproducibility but are not finalized broker
semantics.

## Reproducible coverage

Run from the repository root:

```text
.venv/bin/python scripts/cost_evidence.py --root research-output \
  --output /tmp/cost-evidence.json
```

The generated report is credential-free and contains no order IDs, account IDs,
headers, or exception details. On the inspected tree, the source table is:

| Source | Result | Count | Treatment | Reason for exclusion or limitation |
| --- | --- | ---: | --- | --- |
| Saved quotes / NBBO | missing | 0 | excluded | No quote observations with timestamp, side, feed, and age are saved. |
| Broker-observed fills | missing (or `present_unparsed` for any `FILL` activity) | 0* | excluded pending schema mapping | A `FILL` activity is potential evidence, but requires timestamp, side, feed, quantity, and price mapping. |
| Replay trade JSON | modeled only | 22,764* | inventory only | Replay next-close prices and configured costs are modeled inputs, not execution evidence. |
| Paper account activities | present, non-fill (or `present_unparsed` when `FILL` rows exist) | 1 | excluded from execution calibration | The saved activity is a `JNLC` journal credit with no attributable fill; `FILL` rows require mapping. |
| SQLite run journals | uninspected | 0 | unknown | `run.db` files are located but this focused inventory does not parse their fill rows. |

`*` The count is produced by the script and can change only when a saved artifact is
added or removed. It is not a trade-performance result.

If an account activity snapshot contains `activity_type=FILL`, the script reports it
as `broker_observed_fills` with `present_unparsed` status and excludes it pending field
mapping. It never labels such a row as a non-fill. Replay trades are counted only when
their sibling manifest identifies `source=backtest` and `backend=local`; live or
otherwise unidentified artifacts remain uncounted and unknown.

Missing roots fail with a clear validation error. Malformed JSON, non-object manifests,
non-array trade/activity payloads, and non-object activity rows are retained in the
report's `exclusions` list with an explicit reason; they are never silently treated as
zero observations.

The paper account activity snapshot is a read-only artifact at
`research-output/alpaca-paper-account-2026-jan-aug/account-activities.json`; its
metadata records GET-only retrieval and no submitted order. It cannot establish
spread, slippage, commission, borrow availability/rate, or dividend settlement for
the simulated trades. The saved corporate-action response is likewise evidence of
returned records, not complete ex-date coverage; T01 documents that limitation.

## Component definitions and matching rules

Each component is kept separate:

| Component | Evidence required | Current disposition |
| --- | --- | --- |
| Spread | Same-instrument bid/ask or NBBO, timestamped and feed-identified; compare the executable side at the fill time. | Unknown; no quotes. |
| Slippage | Quote or venue reference timestamped before the execution, with side and quantity; do not derive from OHLC. | Unknown; no matched observations. |
| Commission | Attributable fee field or account cash activity tied to an execution. | Unknown; the saved activity is not a fill. |
| Borrow | Historical availability/locate and rate, timestamped for the short quantity, with day-count and settlement terms. | Unknown; no availability or rate history. |
| Dividend | Authoritative action identity, ex-date entitlement, payment evidence, and lot ownership. | Incomplete; the saved action query does not prove exhaustive coverage or account payment. |

A usable quote/fill match must have timestamp, side, feed, quantity, and quote age.
Any missing or stale field is excluded with its reason. A record discovered after a
decision timestamp cannot be used to decide that earlier eligibility. OHLC bars are
marks and execution-event inputs only; they are never a proxy for the actual spread.
If an observed fill becomes available later, its realized price and fee remain the
execution evidence and the modeled spread/slippage must not be deducted again.

## Frozen scenario labels pending evidence

These are explicit scenario labels inherited from the existing replay protocol, not
measurements and not a threshold sweep:

| Label | Spread | Slippage | Commission | Borrow | Dividend | Provenance |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `base-modeled-v1` | 2 bps round trip | 1 bp per fill | $0/share | unavailable; no free-borrow assumption | unavailable/incomplete | Existing `alpaca-iex-2026` protocol and local `FillPolicy`; scenario only. |
| `adverse-modeled-v1` | 5 bps | 2 bps per fill | $0/share | unavailable; no free-borrow assumption | unavailable/incomplete | Existing `alpaca-iex-2026` protocol and local `FillPolicy`; scenario only. |

The base spread is represented by half the round-trip spread on each side in the
local policy. These labels may be used to reproduce prior modeled artifacts. They do
not freeze future prospective assumptions until the accounting contract is reviewed
and quote/fill evidence or a separately authorized scenario protocol is available.
No cost is inferred from the inventory, and no observed execution-quality claim is
made. The unresolved inputs are handed off to T01/domain review and to a future
read-only evidence collection step.

## Acceptance status

The offline inventory, source/coverage table, component separation, stale/missing
exclusion rules, and explicit base/adverse labels are implemented. Observed cost
coverage is not complete: no saved quotes, broker fills, historical borrow rates, or
account-attributable dividend settlements are available. Therefore T04 is complete
as an evidence-gap inventory and frozen scenario handoff, but not as validation of
execution quality or profitability.
