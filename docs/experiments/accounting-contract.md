# Proposed accounting contract — T01

Prepared September 18, 2026. Specification version: `accounting-contract-v1-draft`.
Status: proposed; independent Astra review and human/domain resolution of the broker
questions below are still required. This document does not implement or activate a policy.
Its deterministic local conventions are proposals for review, not assertions about Alpaca
bookkeeping. Unresolved broker mappings must remain unavailable or explicitly modeled.

Scope is T01 in the research roadmap: USD, whole-share US equity/ETF portfolios, ordinary cash
distributions and short borrow accounting. Frozen votes, RVOL, sizing percentage, entry
and exit logic, fill timing and base/adverse execution-cost scenarios stay unchanged.
January–August 2026 is examined data; any new historical output is a correction or
scenario, not fresh validation. Software reconciliation establishes no profitability.

## 1. Existing behavior and evidence

The following describes the working tree inspected for this specification, including its
existing uncommitted research changes; it is not a claim about only the committed revision.

| Component | Existing behavior that integration must respect |
| --- | --- |
| [Local executor](../../trades/executor.py) | `capital` is starting capital plus closed net trade P&L, not a securities cash balance. `available` subtracts entry notional and entry cost of every open position, both sides. Close P&L includes modeled entry/exit costs and rounds to cents. |
| [Journal](../../db/logger.py) | Schema marker 1; run/source/backend/account scopes, trades and orders exist. `realized_pnl` sums trade P&L, including confirmed partial exits. No distribution/borrow ledger exists. Unknown legacy provenance remains unknown. |
| [Replay](../../backtest.py) | Manifest schema 1; next completed five-minute close fills; timestamp batches share capital, exits precede alphabetical entries. New artifacts must preserve existing runs. |
| `analytics/research_review.py` (current research worktree) | Closed net P&L plus open signed price change less open entry costs. Latest causal completed close marks; no assumed liquidation fee. No dividends, borrow or taxes. |
| `data/review_history.py` (current research worktree) | Requests the bar download's calendar interval through `CorporateActionsClient`, writes the returned action data and a retrieval timestamp. The review does not establish exhaustive ex-date coverage or preserve individual request/page evidence. |

Inspected `tests/test_research_review.py` and `tests/test_replay_performance.py` from the
current research worktree, plus [journal provenance tests](../../tests/test_logger_provenance.py)
and `tests/conftest.py`. These are compatibility anchors, not
evidence that the new rules are implemented.

The only saved corporate-actions response located is
[corporate-actions.json](../../research-output/alpaca-iex-2026-jan-aug/corporate-actions.json),
with [data-review.json](../../research-output/alpaca-iex-2026-jan-aug/data-review.json) and
[bars.meta.json](../../research-output/alpaca-iex-2026-jan-aug/bars.meta.json).
These local, gitignored evidence files are preserved; a fresh checkout may lack them.

| Saved evidence | Observed value |
| --- | --- |
| Retrieval timestamp in review | `2026-09-18T23:23:10.963535+00:00` |
| Requested bar interval | `2026-01-01T00:00:00+00:00` to `2026-09-01T00:00:00+00:00`, end exclusive |
| Bar basis | `alpaca:iex`, raw, UTC bar-start timestamps |
| Action contents | 14 cash dividends; 14 distinct provider IDs; AAPL, META, MSFT, NVDA, QQQ, SPY; no other returned action category |
| Boundary evidence | SPY ID `6c45d8a2-1d04-4d6e-b7e4-be92f8e195ed`: ex-date 2025-12-19, payable/process date 2026-01-30, rate 1.993368 |
| Response SHA-256 | `68ac63b5d547e845a5cbf2572443d2899d726ec6c3a1637a86e51731f9635268` |
| Review SHA-256 | `34e8b614a34f84e4aed9a4a9017331b93a704d6af9652b7dfd6afc30f96b6c8a` |
| Metadata SHA-256 | `2c5a365e4dce3923cfe0c19f248fd7e0aa2d4d4ccf9ab67b082172d50df69acc` |

No action absence, split absence, historical short availability, borrow rate or actual
account cash payment is proved by this inventory. Currency and point-in-time publication
times are absent from these action records. Raw USD bars do not by themselves prove the
currency of every distribution.

## 2. Provider facts and limits

Primary documents below were consulted September 18, 2026. They describe the accessed
versions; their present content does not establish historical account-specific terms.

- Alpaca's [corporate-actions endpoint](https://docs.alpaca.markets/us/reference/corporateactions-1)
  describes inclusive start/end intervals, process-date ordering, IDs and pagination.
  It warns of publication delays. Its `data_quality=complete` is a record filtering
  option, not proof of exhaustive historical events or revisions. No ex-date-completeness
  guarantee is documented there. The saved query's process-date selection therefore
  cannot certify an ex-date population; even matching payable/process dates in all saved
  rows does not make those concepts interchangeable.
- [FINRA Rule 11140](https://www.finra.org/rules-guidance/rulebooks/finra-rules/11140)
  specifies designated ex-dates and different treatment for large distributions and
  late information. Use the authoritative action's ex-date, never a universal
  record-date-minus-one-business-day formula or a guessed settlement lag.
- Alpaca's [daily processes documentation](https://docs.alpaca.markets/us/docs/daily-processes-and-reconcilations)
  says dividend credits can follow the payable date and describes different sandbox
  processing. The payable date is consequently a scheduled date, not evidence of the
  timestamp or amount credited to this paper account.
- Current [margin and short-selling documentation](https://docs.alpaca.markets/us/docs/margin-and-short-selling)
  distinguishes ETB fees, HTB locates and separate daily borrow fees. It gives an HTB
  market-value/rate formula using 360 days, charges for HTB held during a day, and a
  Friday-settlement weekend rule. It describes round-lot charges without settling all
  rounding/base/timing details needed here. Its example locate price is not an annual
  borrow rate. The [October 1, 2025 ETB announcement](https://alpaca.markets/blog/zero-borrow-fees-on-short-selling-etb-stock-shares-alpaca-trading-api/)
  establishes a fee-policy change for eligible Trading API ETB shares, not that any
  particular historical short remained ETB or was available.
- Alpaca's [fractional-trading documentation](https://docs.alpaca.markets/us/docs/fractional-trading)
  describes nearest-penny dividends. It does not specify all tie, aggregation or
  revision rounding rules. The exact decimal rules below are a local proposal.

Do not substitute older versioned short-selling documentation or a current assets flag
for the terms and availability at a historical timestamp. Neither an authenticated
account lookup nor new data acquisition was performed for T01.

## 3. Action identity, revisions and completeness

### Normalized records

Each immutable raw snapshot needs provider/product/endpoint, retrieval time, request
filters, all page receipts and terminal pagination evidence, byte checksum and parser
version. Preserve raw fields even if an SDK model omits them. The saved raw response
contains `id`; the installed SDK's `CashDividend` model does not declare that field.
Do not regenerate a replacement ID from symbol, amount or date.

Normalized records must contain:

- `action_key = (provider, product, provider_action_id)` and verified instrument identity
  (CUSIP/other identifier plus dated symbol mapping). Symbol alone is not identity.
- Type/subtype, currency, per-share amount as a decimal string, special/foreign flags,
  explicit ex-date and effective date where applicable, record date, scheduled payable
  date, process date, any due-bill dates, and cancellation state. Unknown is distinct
  from false or zero. A missing record/payable date does not erase a known entitlement.
- `revision_key`: provider revision if documented, otherwise canonical payload hash;
  raw snapshot checksum, retrieval/first-observed time, any provider publication/update
  time, predecessor/supersession evidence and normalization decisions.
- A separate mapped entitlement cutoff and its policy/evidence. Ex-date/effective date
  is an economic date; process date is not an entitlement cutoff or knowledge time.

An identical action key plus identical normalized payload is a duplicate. Changed
payload under that key is a candidate revision, not a second dividend. A payload hash
proves difference, not revision ordering. Require a documented ordered source revision
or explicit reviewed supersession; otherwise quarantine the conflict. A changed provider
ID is not automatically a new action or a replacement: an auditable cross-reference is
required. Missing IDs or conflicting currency/instrument mapping prevent posting.
Provider guarantees for ID stability across corrections are unresolved.

### Coverage attestation

Track coverage independently for distributions, structural actions, borrow availability,
borrow charges, settlements and marks. Use `verified`, `scenario`, `incomplete`,
`conflict` or `not_applicable`, with reasons, affected symbols/dates/lots and counts.
`not_applicable` requires proven zero exposure; it is not a default for an empty response.

A distribution completeness attestation must reconcile an independently enumerated
ex-date schedule (issuer/exchange or another authorized authoritative source) for every
instrument in the ownership interval against normalized actions. Enumerate corrections,
cancellations, noncash actions and any prior entitlements carried into the window.
Resolve every mismatch. Save that schedule, its provenance, coverage definition and
as-of date. An issuer schedule alone can be incomplete too; describe its scope.

Expanded process-date queries, all pages, overlap and later rechecks are supporting
evidence, not a proof that a fixed lookahead catches every late payment or correction.
Track outstanding entitlements beyond the evaluation end until resolved; payment coverage
can remain incomplete even when ex-date coverage is verified. No arbitrary process-date
buffer establishes finality. The current saved response has `incomplete` coverage.

## 4. Ownership and time boundaries

For the proposed ordinary-distribution local policy, the entitlement snapshot is holdings
immediately before 00:00 America/New_York on the authoritative ex-date. This is a logical
date boundary for the regular-hours-only simulator, not a broker settlement timestamp.
Keep timezone-aware UTC timestamps and exchange-local dates; obtain trading sessions and
early closes from the existing exchange calendar. Do not assume every day is a session.

For a fully filled whole-share lot with cutoff `t_ex`, it qualifies when
`entry_at < t_ex` and `exit_at is absent or exit_at >= t_ex`. Apply timestamped partial
fills strictly before the cutoff to reconstruct remaining quantity; do not inspect
today's `remaining_shares` to infer historical holdings. Entitlement snapshots are
immutable and tied to originating lot/run/account. A hypothetical fill exactly at the
cutoff occurs after entitlement: an entry is excluded and a closing exit retains the
entitlement. Zero holdings produce a known zero without needing an amount/rate only when
the zero exposure itself is established.

Long shares accrue a receivable; short shares accrue a payment-in-lieu liability. Covering
a short or selling a long on/after ex-date does not remove that entitlement/liability.
Buying or opening a short on ex-date does not acquire this ordinary distribution.
Partial post-cutoff exits retain the original entitled quantity; reopening is a new lot.
For split accounts/portfolios, never net entitlements across scopes or long/short lots.

Use completed execution times (`entry_at`/`exit_at`), not signal creation, bar-start,
database insertion, declaration, record, payment or lookup dates. Unknown ordering or
quantity makes the affected entitlement unavailable. These ordinary rules require review
before use for extended hours, nonstandard settlement or broker-observed holdings.

At a shared timestamp: process prior-interval borrow accrual and entitlement boundaries,
then information/settlements available by that timestamp, then the existing exits-before-
entries allocation cycle. Cutoff snapshots precede any fill at the cutoff. Do not reorder
the existing symbol priority or synthesize an executable bar for an accounting event.

### Windows, outstanding balances and exceptions

Use states at `start` and `end`, with flow reporting over `(start, end]`; a state includes
all events at its timestamp. Document conversion from existing bar-start selection to
completed-bar marks. Every report needs opening cash, lots/bases, receivables,
distribution payables, borrow payables and coverage state. P&L is ending minus opening
equity less external contributions, not payment totals received inside the window.
Opening and closing states must also carry correction refund receivables `RF` and
repayment liabilities `LR`, defined below; neither disappears at a window boundary.

A fresh independent replay starts flat with zero inherited entitlements; warmup bars do
not create positions. A continuation imports an explicit scoped opening state. An ex-date
before a flat window gives no entitlement even if payment falls inside it. An ex-date
before a continuation can give payment in the window, but settlement is not new income.
An ex-date inside the window with payment after it contributes to closing equity via the
outstanding balance. Never force payment or liquidation at window end. Post-end cash
reconciliation is a separate tail report; post-end income/costs do not enter window P&L.

Special distributions, due bills, stock dividends, splits/reverse splits, mergers,
spin-offs, rights, returns of capital requiring basis changes, currency conversions,
withholding and ambiguous instrument changes are outside this ordinary mapping. Preserve
their evidence and mark affected accounting unsupported. Do not apply ordinary cutoff
rules to them, turn them into zero cash, or treat a split price jump as P&L. Unsupported
structural actions invalidate affected lot/price-basis reconciliation. Do not silently
drop affected losing trades or sessions. Reports retain the population and show which
metrics cannot be certified; a capital rerun pauses new allocations when state is unknown.

## 5. Accrual, cash settlement and the equity identity

Use distinct nonnegative balance accounts: long distribution receivables `R`, short
distribution payables `L`, borrow payables `B`, correction refund receivables `RF`, and
correction repayment liabilities `LR`. `RF` contains recoverable overpayments of short
distributions or borrow, with those components separately attributed; `LR` contains
excess long distributions received that must be returned. These are supported correction
accounts, not negative values placed in `L`, `B` or `R`. Cash `C` is the local economic cash
book including trade principals; it is not `PaperBroker.capital` or verified broker cash.
Use positive quantities with a separate side. Negative revisions reverse the appropriate
balance/income; a refund claim after overpayment is a receivable, not a negative payable.

| Event | Cash change | Balance change | Economic income/expense |
| --- | ---: | ---: | ---: |
| Long entitlement `d` | 0 | `R += d` | `+d` |
| Long payment `d` | `+d` | `R -= d` | 0 |
| Short entitlement `d` | 0 | `L += d` | `-d` |
| Short payment `d` | `-d` | `L -= d` | 0 |
| Borrow accrual `b` | 0 | `B += b` | `-b` |
| Borrow payment `b` | `-b` | `B -= b` | 0 |
| Downward revision `d` of an already fully paid long distribution | 0 | `LR += d` | `-d` correction |
| Repayment of that excess receipt `d` | `-d` | `LR -= d` | 0 |
| Downward revision `d` of an already fully paid short distribution or borrow charge | 0 | `RF += d` | `+d` correction |
| Refund of that overpayment `d` | `+d` | `RF -= d` | 0 |

Quantity times per-share distribution determines gross economic entitlement, conditional
on verified currency and ordinary treatment. Entitlement records survive position close.
Cash events reference the liability/receivable they discharge. Partial payments discharge
only their matched amount; unexplained differences remain unmatched, never silently
become trading P&L. Actual observed amounts and timestamps remain authoritative evidence
of cash movement; discrepancies need an explicit linked adjustment and reason.

Scheduled payable dates never establish observed payment. Two supported settlement modes
are proposed: `observed`, using attributable account activity; or an explicitly declared
`scenario`, with supplied amount/timestamp. A deterministic fixture may supply midnight
ET on payable date, but there is no historical default assuming this. With neither,
retain the balance as outstanding and mark cash-settlement timing unknown; correctly
known economic entitlement can still be reported. Record separately whether the known
cash subset is sufficient for capital decisions.

The required identities, before display rounding, are:

```text
MV = sum(long quantity * mark) - sum(short quantity * mark)
E  = C + MV + R + RF - L - B - LR

E - E_open - external_net_contributions
   = price_P&L - execution_costs + trade_rounding_bridge
     + distribution_income - short_distribution_expense - borrow_expense
     + explicitly_classified_corrections

E_corrected = E_legacy + cumulative_accounting_cash + R + RF - L - B - LR
```

The last identity is for a flat-start fixed-trade restatement, with zero opening accounting
balances and no external flows; for continuations use changes in all balances and opening
equity. `cumulative_accounting_cash` contains distribution/borrow cash flows, including
correction refunds and repayments, once. The income identity's correction term contains
only deltas not already included in its income/expense terms; never include a revised
income total and the same correction delta together.
`E_legacy` already contains execution costs. Never deduct them again. The income view and
cash-plus-balances view must reconcile; do not add both distribution income and the
receivable to equity. Settlement itself leaves equity unchanged at a fixed market mark.

For the cash-book bridge, a trade of signed quantity `q` posts `-q * entry_price` on
entry and `+q * exit_price` on exit; execution costs are separate debits. Restricted short
proceeds do not increase sizing funds. Existing closed P&L rounding requires the explicit
per-trade bridge `J = saved_pnl - (signed_gross - actual_saved_entry_and_exit_costs)`.
Carry `J` as a labeled local trade-rounding adjustment so `E_legacy` remains exact;
do not infer precise costs from rounded display totals. If unrounded costs/policy inputs
are unavailable, the cash reconstruction has a provenance gap, not a fabricated residual
called dividend or borrow. New accounting does not rewrite saved trade P&L or fee policy.

For broker-observed fills, use confirmed execution prices/fees and actual cash activities
as a separate provenance mode. Never create a theoretical fill to resolve an accounting
difference or deduct modeled spread already embedded in an observed fill.

## 6. Borrow eligibility and costs

Availability and price of borrowing are separate facts. Required availability input is
instrument, account/product, observation and effective times, expiry/validity, shortable
status, ETB/HTB status, available/located quantity if relevant, and source evidence.
It must be available at the entry decision. A present-day flag cannot authorize an old
short; a quoted availability is not proof that a locate or fill occurred.

Required cost input for each charge interval is currency, annualized rate as a decimal
(`0.36`, not `36`), applicable time range, when the rate became known, billable quantity,
valuation price/base and observation time, day-count denominator, covered calendar days,
charge/rounding convention, payment evidence or scenario, and source/revision identifiers.
Locate fees and other one-time fees remain separate components; a fee/share quote cannot
be inserted into an annual-rate formula. Evidence that an applicable fee is zero must
identify the effective fee schedule and historical eligibility. Known zero is not null.

No historical availability archive or account-specific borrow-rate/charge series has
been established by the inspected artifacts. Potential evidence is an authorized saved
dated assets/locate record, contract/fee schedule and account charge statement; read-only
acquisition, if separately authorized, must preserve their provenance. T01 authorizes no
locates, orders, paid feeds or assumption that such archives are obtainable.

### Explicit scenario calculation

A pure calculator may accept a pre-resolved interval with
`fee_exact = billable_quantity * base_price * annual_rate * calendar_days / denominator`.
Splitting intervals is mandatory when quantity/base/rate or policy changes. Count calendar
days, including weekends and holidays designated by the supplied convention; never
substitute exchange-session counts. Charge dates, amount and posting dates are separate.
Zero billable quantity or a verified zero rate yields zero; a missing required nonzero-
exposure input yields unavailable. Negative rates/rebates require a separate supported
policy and cannot silently reduce expenses.

The synthetic fixture policy `SCENARIO-CLOSE-ACT360` explicitly uses actual whole shares
held just after each regular-session close, that session's supplied unadjusted close,
a supplied annual rate valid through the next session, and ACT/360. It charges that
session's calendar date and each non-session date until the next session, with one
calendar-day accrual posted at each following local midnight. A close fill is processed
before the borrow snapshot; holding nothing at close incurs no charge under this scenario.
It is an overnight-only hypothetical model, **not** Alpaca's documented HTB intraday rule.
Non-session prices remain the last specified close with its age recorded; this carry is
part of this named scenario, not permission to forward-fill missing market-session data
or expired rates. DST changes do not change a calendar day into a 23/24 or 25/24 fee.

Broker-compatible billable quantity, round-lot tie/upward rounding, intraday aggregation,
mark source/time, settlement-date entry/cover rules, holiday handling, rate validity and
payment schedule remain unresolved without account/product evidence. Do not map this
scenario to that product by inference. Different conventions must have different IDs.
Base/adverse scenario rates are not selected by T01; the 36% below is arithmetic only.

### Missing inputs

- Fixed-trade restatement keeps every original short. Show known accounting subtotal,
  affected short-days/notional-days and missing availability/rate counts. Fully accounted
  net, associated risk metrics and eligibility conclusions are unavailable, not the
  known subtotal relabeled as net. A supplied rate scenario gives scenario results only.
- A causal capital rerun rejects a new short with unknown availability/rate unless its
  manifest explicitly selects an assumed-availability/rate scenario. State this changes
  the executable candidate population and is not an accounting-only restatement.
- If an existing position's cost or required cash state becomes unknown, continue known
  marks and exits but freeze new portfolio allocations dependent on unknown capital;
  report the incomplete path. Do not invent a zero or punitive rate, forced cover, or
  user risk tolerance. A later correction cannot change already saved decisions.

## 7. Available capital, causality and run modes

The proposed local capital overlay preserves the executor's existing gross-notional
reservation and sizing percentage. Let `K_legacy` be its original capital, `A_cash` the
signed settled distribution/borrow cash since start (including refunds and repayments),
and `L+B+LR` the outstanding costs and repayments:

```text
K_for_sizing = K_legacy + A_cash - L - B - LR
reserved = sum(open entry_notional + open entry_cost)
available = max(0, K_for_sizing - reserved)
budget = max(0, min(K_for_sizing * unchanged_position_pct, available))
shares = floor(budget / (entry_price + unchanged_per_share_execution_cost))
```

Long receivables `R` and correction refund receivables `RF` do not finance trades until
cash is usable under the declared settlement mode. Known short-distribution and borrow
accruals and correction repayment liabilities `LR` reserve funds immediately. Paying an
already reserved liability reduces cash and releases the same reserve, so it does not
deduct sizing capital twice. Unrealized market gains and short-sale proceeds still do not
increase this sizing base. Existing positions are not automatically liquidated because
the overlay makes available capital zero. Negative/unavailable capital is reported.
Opening accounting balances and subsequent cash flows must be included for continuations.
This local rule is not Alpaca buying power, margin lending or a new risk limit.

Every action/rate revision carries both economic effective time and knowledge time.
Knowledge time is when the information was actually available to this run, not ex-date
or provider process date. September-retrieved historical records without earlier
publication evidence cannot be fed to a March decision as if then known.

Use distinct modes and artifact identities:

1. `fixed_trade_restatement`: keep fills, quantities and decisions exactly as saved;
   recompute economic books using the declared evidence/revision as-of. Later information
   can restate historical entitlement/cost at its economic date, with an auditable bridge
   to the original. Report any modeled-capital breach without changing trades. No claim
   that this was the capital path an agent could know at the time.
2. `causal_capital_rerun`: replay frozen strategy rules, consuming only information known
   by each event. Reserve costs and apply payments before subsequent entries. Revised
   capital can change shares and later positions. Retain the decision-time book and a
   separate eventual-economic reconciliation; later corrections enter the decision book
   when learned, not retroactively. Missing historical knowledge/availability prevents
   a verified historical rerun; an explicit hypothetical information scenario is labeled
   as such, with its assumptions frozen before computation.

Perturbing records with knowledge times after a decision must leave that decision,
features and sizing unchanged in the causal mode. Eventual accounting may change.
Neither mode changes earlier saved artifacts or turns examined data into a new holdout.

## 8. Precision, corrections and durable posting

New amounts use decimal strings and exact decimal arithmetic; currency is required.
The proposed USD rule is ROUND_HALF_UP to cents, with symmetric signs by rounding a
nonnegative magnitude then applying its side. Keep the unrounded basis for audit.
Existing floating-point trade calculations and their rounding remain under their original
version; do not silently replace them as part of a cash-flow change.

Aggregate ordinary entitlement by scoped account, action and side, then round once.
Allocate rounded cents to lots in proportion to exact entitlements: floor each positive
allocation to cents, assign remaining cents by largest fractional remainder, tie by stable
lot ID. Sum of lot allocations must equal account total. Never round a per-share rate
before multiplying. Recompute a corrected target from exact inputs, then post only the
difference from the already booked target; do not round each revision delta independently.

For the named borrow scenario, maintain exact cumulative fees for each scope/instrument/
charge-policy billing period. Each daily posting is rounded cumulative target minus
previous rounded target. Splitting an otherwise identical interval must not change the
total. Period boundaries are supplied explicitly, not reset at an evaluation-window
boundary; outstanding fractions and posted totals carry across restarts and windows.
Lot allocations use the same cent-preserving rule. An actual broker invoice can require
a separately evidenced rounding policy and adjustment.

Corrections are append-only reversals/deltas linked to prior revisions and evidence.
Corrected ex-date/quantity requires recomputing the entitlement snapshot from historical
fills and reversing the old attribution. An amount decrease after payment creates a
repayment liability `LR` for a long; after a short or borrow overpayment it creates a
refund receivable `RF`.
A changed payable date reschedules an unobserved scenario event, not an already observed
cash movement. Cancellation reverses only with explicit evidence; it never deletes history.

For each scoped action/side or borrow charge, let `D` be the latest accepted rounded
economic target and `S` be its matched cumulative net settlement magnitude. For a long,
`S` is receipts minus repayments: `R=max(D-S,0)`, `LR=max(S-D,0)`. For a short,
`S` is payments minus refunds: `L=max(D-S,0)`, `RF_short=max(S-D,0)`. For borrow,
the same payment-minus-refund definition gives `B=max(D-S,0)` and
`RF_borrow=max(S-D,0)`; `RF=RF_short+RF_borrow` across attributed charges. All are
nonnegative; do not offset unrelated actions or scopes. A correction changes `D` and
posts the difference from the prior derived balances atomically; it does not change `S`
or cash. Thus a decrease first releases any unpaid amount and creates a correction
account only for the already-paid excess. A later upward revision reduces that correction
account before reestablishing an ordinary balance. A settlement changes `S` and cash,
then the matching balance, with no new income. An unsupported recovery amount or unmatched
cash movement stays a reconciliation gap; it is not a presumed refundable fee.

Logical posting keys must include source/backend/account/run, accounting version, event
kind, action/charge key, accepted revision and entitlement allocation. Payment keys also
include the immutable payment/activity ID. Scenario payments use a deterministic ID tied
to entitlement and declared payment policy. A repeated observation of the same cash
activity is not a new payment. An action revision does not generate a second full payment
for an already settled action; only explicit residual settlement evidence or scenario may
settle a delta. Borrow keys identify charge interval/billing period and revision.
Correction postings must also identify their balance components (`R`, `L`, `B`, `RF`,
`LR`) under one correction event; uniqueness applies to the event and each component.
Recomputing the same accepted target and settlements produces zero delta. Refund and
repayment activities have their own immutable payment IDs linked to that correction and
the original entitlement/charge; replaying an original payment or a refund/repayment
changes neither `S` nor cash a second time. Persist and restore all five balance accounts,
their accepted targets and net-settlement totals, including for closed lots.

Uniqueness, balance changes and durable progress commit atomically; restart/replay must
produce the same balances once. Two conflicting payloads for a payment ID are quarantined,
not resolved by insert order. Replaying to a new scoped run creates its own ledger without
altering old runs. An event, correction and its allocations must reconcile as one unit.

No withholding or personal income/capital-gains taxes are modeled. Report gross pre-tax
economic results; a net observed payment with unknown deductions remains a reconciliation
gap rather than presumed gross income. Long securities lending income, rebates, currency
conversion, margin interest and unobserved broker-specific charges are excluded, explicitly
listed and not silently claimed to be zero. Fully accounted here means the declared
supported distribution/borrow/execution scope, never after-tax broker reconciliation.

## 9. Hand-worked acceptance fixtures

All amounts below are synthetic USD, ordinary actions with verified synthetic currency,
no execution costs, no taxes or external flows, complete synthetic holdings/action coverage,
and zero borrow **only where explicitly excluded to isolate the dividend fixture**.
Each standalone fixture starts with 10,000 cash. Distribution `D1` pays 1.00/share,
ex-date Monday June 8, 2026, cutoff `2026-06-08T04:00:00Z`, scheduled payment June 15.
Payment timestamps in these fixtures are supplied scenario inputs, not inferred broker
facts. Marks and quantities are specified; do not presume real prices fall by a dividend.

### F1 — Long dividend: accrual and payment

Buy 100 at 50 on June 5: `C=5,000`, `MV=5,000`, `E=10,000`. Hold across cutoff.
At ex-date, `R=100*1=100`; supplied mark is 49, so `MV=4,900` and
`E=5,000+4,900+100=10,000`. Price P&L is -100 and distribution income +100.
On supplied June 15 payment with mark still 49: `C=5,100`, `R=0`, `E=10,000`.
Payment income is zero; adding another +100 would be an error.

### F2 — Short dividend: liability and payment

Short 100 at 50 on June 5: `C=15,000`, `MV=-5,000`, `E=10,000`. Borrow is
excluded for this isolated distribution fixture. At cutoff accrue `L=100`; mark 49
gives `MV=-4,900`, so `E=15,000-4,900-100=10,000`. Price P&L +100 offsets
distribution expense -100. On supplied payment: `C=14,900`, `L=0`, `E=10,000`.
The cash debit is not a second -100 expense.

### F3 — Pre-ex-date close

Buy 100 at 50, then sell all at 51 at Friday June 5 close, before cutoff.
`C=10,100`, quantity at cutoff is zero, `R=L=0`; June 15 produces no payment and
`E=10,100`. Short/cover at those prices instead yields `C=9,900`, `L=0`,
`E=9,900` (borrow excluded here). No original-entry quantity survives a pre-cutoff close.

### F4 — Entry on ex-date, including exact boundary

Buy 100 at 49 on June 8 after cutoff: `C=5,100`, `MV=4,900`, `R=0`,
`E=10,000` at that mark. Shorting at 49 instead gives `C=14,900`, `MV=-4,900`,
`L=0`, `E=10,000`. Neither receives/owes `D1`. A synthetic entry exactly at
`04:00:00Z` also has zero entitlement. An existing 100-share lot closed exactly at
that timestamp retains 100/share-side entitlement because the snapshot comes first.

### F5 — Close before pay date; retained entitlement and windows

Continue F1 and sell at 49 on June 10: `C=9,900`, `MV=0`, `R=100`, `E=10,000`.
June 15 payment gives `C=10,000`, `R=0`, `E=10,000`. For F2, cover at 49 on
June 10: `C=10,100`, `L=100`, `E=10,000`; payment then gives `C=10,000`, `L=0`.
The closed lot retains attribution even if another lot opens before payment.

If only 40 long shares are sold after cutoff, cash becomes `5,000+40*49=6,960`,
remaining mark is `60*49=2,940`, and `R=100`, so equity remains 10,000. Entitlement
is not reduced to 60. If 40 were sold before cutoff instead, only 60 qualify: `R=60`.

A June 12 window end reports the closed long's 9,900 cash plus 100 receivable. A
continuation from that state to June 16 has equity change zero even though +100 cash
arrives. A new flat window beginning June 12 receives nothing: no inherited ownership
or receivable. The saved SPY December-ex/January-pay record likewise does not create
income for a flat January start. A non-flat January continuation would need its actual
opening entitlement evidence.

### F6 — Borrow over a weekend

Use `SCENARIO-CLOSE-ACT360` only: short 100 at 50 Friday June 5 before close,
remain short at Friday close, supplied base 50, annual rate `0.36` valid Friday through
Monday, denominator 360, and cover Monday June 8 at 50 before close. Friday, Saturday
and Sunday each accrue `100*50*0.36/360 = 5.00`; total is 15.00, not 5.00.
Accruals are posted at the following local midnights, so by Monday 00:00 `B=15`.
Before cover, `C=15,000`, `MV=-5,000`, `B=15`, `E=9,985`. After cover,
`C=10,000`, `MV=0`, `B=15`, `E=9,985`. Supplied later borrow payment gives
`C=9,985`, `B=0`, `E=9,985`. No Monday-close holding means no Monday charge
under this fixture policy; that conclusion must not be reused as a broker HTB rule.

### F7 — Missing rate or availability

Keep F6 quantity/base and three charge days, but set rate to null. Notional-days are
`100*50*3=15,000 USD-days`; missing-rate days are 3 and the fee is **unavailable**.
Known pre-borrow equity is 10,000; fully accounted equity is unavailable, not 10,000.
Providing scenario `0.36` changes only that scenario's result to 9,985. A verified
applicable zero rate would instead give exactly zero cost. With zero billable quantity,
the fee is zero without a rate, because exposure is proven absent. Unknown availability
still prevents an entry being called historically executable even when cost is known.

### F8 — Duplicate, corrected and already-paid action

Hold 100 long shares for action key `D1`. Revision A is 1.00/share, so accrue 100.
Read A twice or restart: added amount on the second application is 0; `R=100`.
An explicitly superseding revision B is 1.20/share: corrected target 120, delta +20,
so `R=120`, total distribution income 120. At the F1 mark 49, equity is 10,020.
A payment of 120 moves `C` from 5,000 to 5,120 and `R` to zero; equity stays 10,020.

Alternatively A was already paid: `C=5,100`, `R=0`. B creates only `R=20`; it
does not repeat the 100 cash credit. A separately evidenced 20 payment completes it.
Repeated B or either payment ID changes nothing. For 100 short shares, A gives `L=100`;
B adds 20 expense/liability, with the opposite equity sign. If a paid long amount 100
is corrected to 80, recognize -20 income and a 20 repayment liability until paid;
never erase the original credit. Unordered conflicting B or a changed ID with no
supersession evidence is `conflict`, with no guessed second entitlement.

### F9 — Decimal ties, account aggregation and cumulative borrow rounding

Three shares at `0.335` have exact entitlement `1.005`, rounded target `1.01` for a
long or expense `1.01` for a short. Two one-share lots at `0.005` each aggregate to
`0.010`, rounded once to `0.01`, not `0.02`; the lower stable lot ID receives the tie
cent. A revision from exact target `1.004` to `1.005` changes rounded target `1.00`
to `1.01`, so post `+0.01`, not rounded delta `0.001 = 0.00`.

For exact daily borrow `0.004` over three days in one billing period, cumulative targets
are `0.004`, `0.008`, `0.012`; rounded targets are `0.00`, `0.01`, `0.01`.
Daily postings are `0.00`, `0.01`, `0.00`, total `0.01`. Rounding each day to zero
or resetting the cumulative accumulator at a window boundary is incorrect.

### F10 — Cost reserves and capital without changing sizing percentage

Let legacy capital be 10,000, existing reservation 5,000, position percentage 10%,
pending short distribution 100 and borrow 15, accounting cash so far zero.
`K_for_sizing=9,885`, `available=4,885`, `budget=min(988.50,4,885)=988.50`.
At entry 50 with no execution cost, buy at most `floor(988.50/50)=19` shares,
versus 20 before the costs. Payment of 115 sets accounting cash to -115 and payables
to zero: the same capital/budget remains. A long receivable 100 adds nothing to sizing;
its later 100 cash payment raises sizing capital by 100. A fixed-trade restatement keeps
the original 20 shares and flags the breach; only a separately identified rerun takes 19.

### F11 — Paid corrections, refunds and repayments reconcile through settlement

Continue the fully closed, paid long in F5: `K_legacy=9,900`, `C=10,000`,
`A_cash=100`, all balances zero, so `E=K_for_sizing=10,000`. Correct its target
from 100 to 80 while net receipts remain 100: `R=max(80-100,0)=0` and
`LR=max(100-80,0)=20`. Cash stays 10,000; equity and sizing capital both become
`10,000-20=9,980`. Economic reconciliation is price P&L -100 plus original income
100 plus correction -20 = -20. With no open positions, available capital is 9,980.
Repay 20 in a separately evidenced event: `C=9,980`, `A_cash=80`, net receipts
`S=80`, `LR=0`; `E=9,980` and `K_for_sizing=9,900+80=9,980` are unchanged.
Applying the revision or either payment ID twice leaves every amount unchanged.

For the fully closed, paid short in F5, `K_legacy=10,100`, `C=10,000`,
`A_cash=-100` and all balances zero. Correct its target from 100 to 80 while net
payments remain 100: `L=max(80-100,0)=0`, `RF=max(100-80,0)=20`. Equity is
`10,000+20=10,020`; price P&L +100 minus original expense 100 plus correction
20 = +20. Pending receipt, sizing and available capital stay `10,100-100=10,000`
because `RF` cannot fund entries. Receive a separately evidenced refund of 20:
`C=10,020`, `A_cash=-80`, net payments `S=80`, `RF=0`. Equity remains 10,020;
sizing and available capital rise to `10,100-80=10,020`. The cash refund creates
no second income. Duplicate revision/refund/payment events again have zero effect.

If either example's downward revision arrived while only 60 had settled instead,
the corrected target 80 would leave an ordinary balance of 20 (`R` long or `L` short),
with `LR=RF=0`; it must not create a 20 repayment/refund claim as well. For an opening
window state carrying `LR=20` or `RF=20`, subsequent matching settlement leaves equity
unchanged by the same calculations; the correction belongs to its own recognition period.

## 10. Versioning, implementation handoff and unresolved decisions

Propose `accounting_version=2` for outputs implementing the reviewed contract, distinct
from the current implicit legacy version 1. Proposed additive DB migration marker and
manifest schema are 2; T03 must check for intervening versions rather than collide with
another migration. A draft specification is not migration completion. Never relabel old
records as fully accounted or overwrite old manifests, SQLite rows or result directories.

Additive storage needs immutable action revisions, scoped entitlement allocations,
cash-flow postings/corrections, charge intervals, matched settlements, opening snapshots
and coverage exceptions. Link trades rather than folding accounting cash into legacy
`trades.pnl`; reports can derive an explicitly named all-in lot P&L. `realized_pnl` alone
cannot restore corrected capital. Closed lots with outstanding balances must restore.

Every new artifact must record contract checksum/version, schema/code/data identities,
source/backend/account/run, original run linkage, evidence as-of and checksums, coverage
counts, mode, rounding, calendar/timezone, price-adjustment basis, settlement policy,
borrow/availability assumptions, trade-rounding bridge and excluded components. Keep
raw unadjusted prices for separately posted distributions; adjusted total-return prices
plus these distributions would double count. T03 must test no-applicable-flow equality
to the old executor/review, including closed trade rounding and open entry costs.

| Open item | Required resolution / permitted work meanwhile |
| --- | --- |
| Independent accounting review | Separate Astra reviews this proposal and every fixture. The author does not self-approve. |
| Human/domain broker mapping | Resolve action correction/ID guarantees, cash payment matching/timing, short payment-in-lieu posting, rounding and charge conventions before claiming broker-compatible accounting. Local parameterized fixtures can be reviewed independently. |
| Action completeness and currency | Obtain and reconcile an authoritative ex-date/instrument schedule and currency evidence. Saved response alone remains incomplete. |
| Historical borrow eligibility/rates | Supply dated account/product evidence or freeze explicitly hypothetical scenarios. Current ETB policy alone is insufficient. |
| Borrow charge details | Resolve billable quantity/base, round lots, daily/intraday/settlement/holiday rules, rate validity, posting/payment and billing-period rounding. The named fixture scenario is not that resolution. |
| Historical knowledge times | September snapshots alone support eventual corrections; causal March–August accounting decisions require earlier availability evidence or an explicitly hypothetical information scenario. |
| Cash availability and unsupported actions | Preserve unknown balances; no guessed payment, structural-action handling or buying power. Mark dependent results unavailable. |
| T02/T03 dependency | No production work in T01. After review, implement only settled pure rules/scenarios; retain unresolved mappings as explicit inputs or unavailable states. |

### Acceptance and verification handoff

All eight requested example categories are supplied: F1 long, F2 short, F3 pre-ex close,
F4 ex-date entry, F5 close-before-pay, F6 weekend borrow, F7 missing rate, F8 duplicate/
corrected action. F9–F11 add rounding, capital and paid-correction settlement checks.
Identities include open and
closed positions, outstanding entitlements and window continuity. Uncertain conventions
are identified above; no broker-specific missing convention is silently selected.

Documentation checks should verify all local links when the referenced evidence is
present, the three saved checksums/counts, headings/fixture coverage, decimal arithmetic
and `git diff --check`. No backend tests are required for this documentation-only patch;
running them would not validate broker semantics. The proposed specification and examples
are ready for the assigned independent review. Final T01 acceptance remains subject to
that review and explicit disposition of the human/domain dependencies; historical
accounting completeness is not established by this document.
