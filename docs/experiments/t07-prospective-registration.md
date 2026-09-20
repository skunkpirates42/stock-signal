# T07 prospective registration

The T07 runner is fail-closed. A file is eligible for a regime run only when it has
`status: "registered"`, a single holdout period matching the windows file, and explicit
operator, universe, feed, calendar, accounting-policy, cost-policy, and risk-limit fields.
The checked-in template remains blocked and contains no dates or coverage claim.

Before collection, an operator should:

1. Copy `t07-regime-registration.template.json` into a dated, immutable output directory.
2. Set the operator identity, symbols, read-only feed identity, exchange calendar, and the
   accounting and cost policy versions that will be used for the entire period.
3. Set non-negative limits for marked drawdown, gross exposure, turnover, adverse loss, and
   stale-data fraction. These are human risk decisions and must not be inferred from results.
4. Set `status` to `registered` only after the development and holdout windows are frozen and
   the holdout dates match the windows file exactly.
5. Run the regime comparison with `--experiment regime --registration <file>` into a new,
   empty output directory. Do not reuse a viewed historical holdout as a fresh evaluation.

Registration authorizes a frozen evaluation definition; it does not start an unattended
collector, submit broker orders, or establish profitability. Collection remains paper-only
and must produce complete marked accounting, cost, borrow/dividend, stale-data, and journal
evidence before the T06 review can make a decision.
