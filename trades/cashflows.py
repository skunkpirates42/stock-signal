"""Pure, deterministic cash-flow calculations for the accounting fixtures.

This module deliberately has no broker, database, clock, or network dependency.  It
models the local rules in ``accounting-contract-v1-draft``.  In particular, an
ordinary distribution is an economic accrual at the ex-date and a settlement is a
separate cash event.  The result keeps both values so a settlement cannot be counted
as a second item of income.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CENT = Decimal("0.01")
ZERO = Decimal("0")


def decimal(value: object) -> Decimal:
    """Convert a decimal input without introducing binary floating-point arithmetic."""

    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        result = Decimal(value)
    elif isinstance(value, float):
        raise TypeError("float inputs are rejected; use Decimal or decimal text")
    else:
        raise TypeError("cash-flow amounts must be Decimal, int, or decimal text")
    if not result.is_finite():
        raise ValueError("cash-flow amounts must be finite")
    return result


def round_cents(value: object) -> Decimal:
    """Round a signed amount symmetrically, using the contract's HALF_UP rule."""

    amount = decimal(value)
    magnitude = abs(amount).quantize(CENT, rounding=ROUND_HALF_UP)
    return magnitude if amount >= ZERO else -magnitude


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class Holding:
    """A scoped, signed-by-side lot used for entitlement snapshots."""

    lot_id: str
    symbol: str
    side: str
    quantity: Decimal
    entry_at: datetime
    exit_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.side not in ("LONG", "SHORT"):
            raise ValueError("side must be LONG or SHORT")
        quantity = decimal(self.quantity)
        if quantity < ZERO:
            raise ValueError("quantity must be non-negative")
        _require_aware(self.entry_at, "entry_at")
        if self.exit_at is not None:
            _require_aware(self.exit_at, "exit_at")
            if self.exit_at < self.entry_at:
                raise ValueError("exit_at cannot precede entry_at")
        object.__setattr__(self, "quantity", quantity)


@dataclass(frozen=True)
class DistributionAction:
    """An immutable action revision.

    A changed payload with no ``supersedes_revision`` is a conflict.  That prevents
    an unordered provider correction from becoming a second distribution.
    """

    action_id: str
    symbol: str
    ex_at: datetime
    per_share: Optional[Decimal]
    currency: Optional[str] = None
    revision_id: str = "initial"
    supersedes_revision: Optional[str] = None
    knowledge_at: Optional[datetime] = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        _require_aware(self.ex_at, "ex_at")
        if self.knowledge_at is not None:
            _require_aware(self.knowledge_at, "knowledge_at")
        if self.per_share is not None:
            rate = decimal(self.per_share)
            if rate < ZERO:
                raise ValueError("ordinary distribution rate cannot be negative")
            object.__setattr__(self, "per_share", rate)


@dataclass(frozen=True)
class Settlement:
    """A matched settlement for one action.

    ``kind=payment`` means a receipt for LONG or a payment-in-lieu for SHORT.
    ``kind=refund`` means the reverse cash direction.  Amount is always a
    non-negative magnitude.
    """

    payment_id: str
    action_id: str
    amount: Optional[Decimal]
    occurred_at: datetime
    kind: str = "payment"
    knowledge_at: Optional[datetime] = None
    side: Optional[str] = None
    currency: Optional[str] = None

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        if self.knowledge_at is not None:
            _require_aware(self.knowledge_at, "knowledge_at")
        if self.kind not in ("payment", "refund"):
            raise ValueError("settlement kind must be payment or refund")
        if self.side is not None and self.side not in ("LONG", "SHORT"):
            raise ValueError("settlement side must be LONG, SHORT, or omitted")
        if self.amount is not None:
            amount = decimal(self.amount)
            if amount < ZERO:
                raise ValueError("settlement amount must be non-negative")
            object.__setattr__(self, "amount", amount)


@dataclass(frozen=True)
class TimeWindow:
    """A reporting window whose flows are selected by ``(start, end]``."""

    start: datetime
    end: datetime
    opening_receivables: Mapping[Tuple[str, str], Decimal] = field(default_factory=dict)
    opening_payables: Mapping[Tuple[str, str], Decimal] = field(default_factory=dict)
    opening_borrow_payables: Mapping[str, Decimal] = field(default_factory=dict)
    opening_refund_receivables: Mapping[Tuple[str, str], Decimal] = field(default_factory=dict)
    opening_repayment_liabilities: Mapping[Tuple[str, str], Decimal] = field(default_factory=dict)
    opening_targets: Mapping[Tuple[str, str], Decimal] = field(default_factory=dict)
    opening_settled: Mapping[Tuple[str, str], Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(self.start, "window.start")
        _require_aware(self.end, "window.end")
        if self.end < self.start:
            raise ValueError("window.end cannot precede window.start")
        for balances in (
            self.opening_receivables,
            self.opening_payables,
            self.opening_borrow_payables,
            self.opening_refund_receivables,
            self.opening_repayment_liabilities,
            self.opening_targets,
        ):
            for value in balances.values():
                if decimal(value) < ZERO:
                    raise ValueError("opening accounting balances must be non-negative")

    def contains(self, timestamp: datetime) -> bool:
        return self.start < timestamp <= self.end


@dataclass(frozen=True)
class DistributionResult:
    status: str
    side: str
    action_id: str
    qualified_quantity: Decimal
    exact_target: Optional[Decimal]
    target: Optional[Decimal]
    settled: Optional[Decimal]
    cash_delta: Optional[Decimal]
    economic_income: Optional[Decimal]
    receivable: Optional[Decimal]
    payable: Optional[Decimal]
    refund_receivable: Optional[Decimal]
    repayment_liability: Optional[Decimal]
    lot_allocations: Mapping[str, Decimal] = field(default_factory=dict)
    included_settlements: Tuple[str, ...] = ()
    unknown_reasons: Tuple[str, ...] = ()
    accepted_revision: Optional[str] = None


@dataclass(frozen=True)
class DistributionBook:
    """Results keyed by ``(action_id, side)`` plus causal visibility metadata."""

    results: Mapping[Tuple[str, str], DistributionResult]
    visible_action_ids: Tuple[str, ...]
    hidden_action_ids: Tuple[str, ...]


@dataclass(frozen=True)
class BorrowInterval:
    """A fully specified synthetic borrow charge interval.

    ``end`` is exclusive for calendar-day counting.  This is the named
    ``SCENARIO-CLOSE-ACT360`` arithmetic fixture, not a claim about broker billing.
    """

    interval_id: str
    quantity: Decimal
    base_price: Decimal
    annual_rate: Optional[Decimal]
    start: datetime
    end: datetime
    denominator: Decimal = Decimal("360")
    knowledge_at: Optional[datetime] = None
    currency: Optional[str] = None

    def __post_init__(self) -> None:
        quantity = decimal(self.quantity)
        base = decimal(self.base_price)
        denominator = decimal(self.denominator)
        if quantity < ZERO or base < ZERO:
            raise ValueError("borrow quantity and base price must be non-negative")
        if denominator <= ZERO:
            raise ValueError("borrow denominator must be positive")
        _require_aware(self.start, "borrow.start")
        _require_aware(self.end, "borrow.end")
        if self.end < self.start:
            raise ValueError("borrow.end cannot precede borrow.start")
        if self.knowledge_at is not None:
            _require_aware(self.knowledge_at, "borrow.knowledge_at")
        rate = None if self.annual_rate is None else decimal(self.annual_rate)
        if rate is not None and rate < ZERO:
            raise ValueError("negative borrow rates require a separate rebate policy")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "base_price", base)
        object.__setattr__(self, "denominator", denominator)
        object.__setattr__(self, "annual_rate", rate)


@dataclass(frozen=True)
class BorrowResult:
    status: str
    interval_id: str
    calendar_days: int
    notional_days: Decimal
    exact_fee: Optional[Decimal]
    rounded_target: Optional[Decimal]
    posted_fee: Optional[Decimal]
    daily_exact: Tuple[Decimal, ...] = ()
    cumulative_postings: Tuple[Decimal, ...] = ()
    missing_rate_days: int = 0
    unknown_reasons: Tuple[str, ...] = ()
    settled: Optional[Decimal] = None
    cash_delta: Optional[Decimal] = None
    economic_expense: Optional[Decimal] = None
    payable: Optional[Decimal] = None
    refund_receivable: Optional[Decimal] = None
    included_settlements: Tuple[str, ...] = ()


@dataclass(frozen=True)
class BorrowSettlement:
    """A payment or refund matched to one borrow charge interval."""

    payment_id: str
    charge_id: str
    amount: Optional[Decimal]
    occurred_at: datetime
    kind: str = "payment"
    knowledge_at: Optional[datetime] = None
    currency: Optional[str] = None

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        if self.knowledge_at is not None:
            _require_aware(self.knowledge_at, "knowledge_at")
        if self.kind not in ("payment", "refund"):
            raise ValueError("borrow settlement kind must be payment or refund")
        if self.amount is not None:
            amount = decimal(self.amount)
            if amount < ZERO:
                raise ValueError("borrow settlement amount must be non-negative")
            object.__setattr__(self, "amount", amount)


def _dedupe_settlements(settlements: Iterable[Settlement]) -> Tuple[Tuple[Settlement, ...], Tuple[str, ...]]:
    by_id: Dict[str, Settlement] = {}
    conflicts: List[str] = []
    for settlement in settlements:
        prior = by_id.get(settlement.payment_id)
        if prior is None:
            by_id[settlement.payment_id] = settlement
        elif prior != settlement:
            conflicts.append(settlement.payment_id)
    return tuple(by_id.values()), tuple(sorted(set(conflicts)))


def _dedupe_borrow_settlements(
    settlements: Iterable[BorrowSettlement],
) -> Tuple[Tuple[BorrowSettlement, ...], Tuple[str, ...]]:
    by_id: Dict[str, BorrowSettlement] = {}
    conflicts: List[str] = []
    for settlement in settlements:
        prior = by_id.get(settlement.payment_id)
        if prior is None:
            by_id[settlement.payment_id] = settlement
        elif prior != settlement:
            conflicts.append(settlement.payment_id)
    return tuple(by_id.values()), tuple(sorted(set(conflicts)))


def _accepted_actions(actions: Iterable[DistributionAction]) -> Tuple[Tuple[DistributionAction, ...], Tuple[str, ...]]:
    grouped: Dict[str, List[DistributionAction]] = {}
    for action in actions:
        grouped.setdefault(action.action_id, []).append(action)

    accepted: List[DistributionAction] = []
    conflicts: List[str] = []
    for action_id, revisions in grouped.items():
        by_revision: Dict[str, DistributionAction] = {}
        for revision in revisions:
            prior = by_revision.get(revision.revision_id)
            if prior is None:
                by_revision[revision.revision_id] = revision
            elif prior != revision:
                conflicts.append(action_id)
        if action_id in conflicts:
            continue
        values = tuple(by_revision.values())
        if len(values) == 1:
            accepted.append(values[0])
            continue
        # Follow an explicit supersession chain.  Any branch or unlinked revision is
        # quarantined as a conflict rather than resolved by input order.
        roots = [revision for revision in values if revision.supersedes_revision is None]
        if len(roots) != 1:
            conflicts.append(action_id)
            continue
        current = roots[0]
        remaining = dict(by_revision)
        del remaining[current.revision_id]
        while remaining:
            children = [r for r in remaining.values() if r.supersedes_revision == current.revision_id]
            if len(children) != 1:
                conflicts.append(action_id)
                break
            current = children[0]
            del remaining[current.revision_id]
        else:
            accepted.append(current)
    return tuple(accepted), tuple(sorted(set(conflicts)))


def _known_by(value: Optional[datetime], decision_time: Optional[datetime]) -> bool:
    if decision_time is None:
        return True
    _require_aware(decision_time, "decision_time")
    return value is not None and value <= decision_time


def _qualified(holding: Holding, action: DistributionAction) -> bool:
    if holding.symbol != action.symbol or holding.quantity == ZERO:
        return False
    # Entry exactly at the cutoff is after the entitlement snapshot; an exit at the
    # cutoff is processed after the snapshot and therefore remains entitled.
    return holding.entry_at < action.ex_at and (
        holding.exit_at is None or holding.exit_at >= action.ex_at
    )


def allocate_cents(exact_by_lot: Mapping[str, Decimal], rounded_total: Optional[Decimal] = None) -> Dict[str, Decimal]:
    """Allocate one rounded aggregate target to lots by largest remainder.

    Inputs are non-negative exact magnitudes.  Stable lot IDs break equal remainder
    ties, making replay and restart results identical.
    """

    exact = {lot_id: decimal(value) for lot_id, value in exact_by_lot.items() if decimal(value) > ZERO}
    if not exact:
        return {}
    aggregate = sum(exact.values(), ZERO)
    target = round_cents(aggregate if rounded_total is None else rounded_total)
    if target < ZERO:
        raise ValueError("allocation target must be non-negative")
    floors: Dict[str, Decimal] = {}
    remainders: List[Tuple[Decimal, str]] = []
    for lot_id, value in exact.items():
        floor_value = value.quantize(CENT, rounding=ROUND_DOWN)
        floors[lot_id] = floor_value
        remainders.append((value - floor_value, lot_id))
    remaining_cents = int((target - sum(floors.values(), ZERO)) / CENT)
    if remaining_cents < 0 or remaining_cents > len(floors):
        raise ValueError("rounded allocation cannot be reconciled to its lot amounts")
    result = dict(floors)
    for _, lot_id in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remaining_cents]:
        result[lot_id] += CENT
    return result


def _unknown_result(side: str, action_id: str, quantity: Decimal, reasons: Sequence[str], revision: Optional[str] = None) -> DistributionResult:
    return DistributionResult(
        status="unknown",
        side=side,
        action_id=action_id,
        qualified_quantity=quantity,
        exact_target=None,
        target=None,
        settled=None,
        cash_delta=None,
        economic_income=None,
        receivable=None,
        payable=None,
        refund_receivable=None,
        repayment_liability=None,
        unknown_reasons=tuple(sorted(set(reasons))),
        accepted_revision=revision,
    )


def _distribution_for_side(
    holdings: Sequence[Holding],
    action: DistributionAction,
    side: str,
    settlements: Sequence[Settlement],
    window: Optional[TimeWindow],
) -> DistributionResult:
    qualified = [holding for holding in holdings if holding.side == side and _qualified(holding, action)]
    exact_by_lot = {holding.lot_id: holding.quantity * action.per_share for holding in qualified} if action.per_share is not None else {}
    quantity = sum((holding.quantity for holding in qualified), ZERO)
    opening_key = (action.action_id, side)
    opening_receivable = ZERO if window is None else decimal(window.opening_receivables.get(opening_key, ZERO))
    opening_payable = ZERO if window is None else decimal(window.opening_payables.get(opening_key, ZERO))
    opening_refund = ZERO if window is None else decimal(window.opening_refund_receivables.get(opening_key, ZERO))
    opening_repayment = ZERO if window is None else decimal(window.opening_repayment_liabilities.get(opening_key, ZERO))
    inherited = any((opening_receivable, opening_payable, opening_refund, opening_repayment))
    in_window = window is None or window.contains(action.ex_at)
    future = window is not None and action.ex_at > window.end
    if quantity == ZERO and not inherited and not future:
        return DistributionResult(
            status="known",
            side=side,
            action_id=action.action_id,
            qualified_quantity=ZERO,
            exact_target=ZERO,
            target=ZERO,
            settled=ZERO,
            cash_delta=ZERO,
            economic_income=ZERO,
            receivable=ZERO,
            payable=ZERO,
            refund_receivable=ZERO,
            repayment_liability=ZERO,
            accepted_revision=action.revision_id,
        )
    if future:
        exact_target = ZERO
        target = ZERO
    elif action.cancelled:
        target = ZERO
        exact_target = ZERO
    elif not in_window and inherited:
        # The opening snapshot is authoritative for a continuation.  The action's
        # original rate is not needed again when its economic event predates start.
        exact_target = ZERO
        target = ZERO
    elif action.per_share is None:
        return _unknown_result(side, action.action_id, quantity, ("missing_distribution_rate",), action.revision_id)
    elif not action.currency:
        return _unknown_result(side, action.action_id, quantity, ("missing_currency",), action.revision_id)
    else:
        exact_target = sum(exact_by_lot.values(), ZERO)
        target = round_cents(exact_target)

    relevant = [
        settlement for settlement in settlements
        if settlement.action_id == action.action_id
        and (settlement.side == side or settlement.side is None)
    ]
    ambiguous_unscoped = [
        settlement for settlement in relevant
        if settlement.side is None
        and any(
            holding.side != side and _qualified(holding, action)
            for holding in holdings
        )
    ]
    if ambiguous_unscoped:
        return _unknown_result(side, action.action_id, quantity, ("unscoped_settlement_with_multiple_sides",), action.revision_id)
    if window is not None:
        relevant = [settlement for settlement in relevant if window.contains(settlement.occurred_at)]
    deduped, settlement_conflicts = _dedupe_settlements(relevant)
    if settlement_conflicts:
        return _unknown_result(side, action.action_id, quantity, ("conflicting_settlement:" + settlement_conflicts[0],), action.revision_id)
    if any(settlement.amount is None for settlement in deduped):
        return _unknown_result(side, action.action_id, quantity, ("missing_settlement_amount",), action.revision_id)
    if any(settlement.currency is None for settlement in deduped):
        return _unknown_result(side, action.action_id, quantity, ("missing_settlement_currency",), action.revision_id)
    if any(settlement.currency != action.currency for settlement in deduped):
        return _unknown_result(side, action.action_id, quantity, ("settlement_currency_mismatch",), action.revision_id)
    net_settlement = sum(
        (settlement.amount if settlement.kind == "payment" else -settlement.amount for settlement in deduped),
        ZERO,
    )
    prior_settled = ZERO
    if window is not None:
        prior_settled = decimal(window.opening_settled.get((action.action_id, side), ZERO))
    settled_total = prior_settled + net_settlement
    # ``target`` is the new target delta for this action.  Opening balances carry
    # prior accruals and corrections across the continuation boundary.
    prior_target_key = (action.action_id, side)
    has_prior_target = window is not None and prior_target_key in window.opening_targets and not in_window
    target_delta = target - decimal(window.opening_targets[prior_target_key]) if has_prior_target else target
    if side == "LONG":
        cash_delta = net_settlement
        net_balance = opening_receivable - opening_repayment + target_delta - net_settlement
        receivable = max(net_balance, ZERO)
        repayment = max(-net_balance, ZERO)
        return DistributionResult(
            status="known", side=side, action_id=action.action_id,
            qualified_quantity=quantity, exact_target=exact_target, target=target,
            settled=settled_total, cash_delta=cash_delta,
            economic_income=target if in_window else ZERO,
            receivable=receivable, payable=ZERO, refund_receivable=ZERO,
            repayment_liability=repayment,
            lot_allocations=allocate_cents(exact_by_lot, target),
            included_settlements=tuple(sorted(settlement.payment_id for settlement in deduped)),
            accepted_revision=action.revision_id,
        )
    cash_delta = -net_settlement
    net_balance = opening_payable - opening_refund + target_delta - net_settlement
    payable = max(net_balance, ZERO)
    refund = max(-net_balance, ZERO)
    return DistributionResult(
        status="known", side=side, action_id=action.action_id,
        qualified_quantity=quantity, exact_target=exact_target, target=target,
        settled=settled_total, cash_delta=cash_delta,
        economic_income=-target if in_window else ZERO,
        receivable=ZERO, payable=payable, refund_receivable=refund,
        repayment_liability=ZERO,
        lot_allocations=allocate_cents(exact_by_lot, target),
        included_settlements=tuple(sorted(settlement.payment_id for settlement in deduped)),
        accepted_revision=action.revision_id,
    )


def calculate_distributions(
    holdings: Iterable[Holding],
    actions: Iterable[DistributionAction],
    settlements: Iterable[Settlement] = (),
    *,
    decision_time: Optional[datetime] = None,
    window: Optional[TimeWindow] = None,
) -> DistributionBook:
    """Calculate long/short accruals and settlements without changing decisions.

    With ``decision_time`` set, records whose knowledge time is later (or absent) are
    hidden from this causal view.  Calling without it computes the eventual economic
    view.  Thus a later correction can change eventual accounting while leaving the
    earlier causal result untouched.
    """

    all_actions = tuple(actions)
    # Resolve revisions using only records available to the decision.  A later
    # superseding revision must not replace the earlier causal record.  The
    # eventual view resolves the complete chain.
    candidate_actions = tuple(
        action for action in all_actions if _known_by(action.knowledge_at, decision_time)
    )
    accepted, conflicts = _accepted_actions(candidate_actions)
    visible: List[DistributionAction] = []
    hidden_ids: List[str] = []
    for action in accepted:
        visible.append(action)
    visible_ids = {action.action_id for action in visible}
    hidden_ids.extend(
        action.action_id
        for action in all_actions
        if action.action_id not in visible_ids
        and not _known_by(action.knowledge_at, decision_time)
    )
    results: Dict[Tuple[str, str], DistributionResult] = {}
    holding_tuple = tuple(holdings)
    settlement_tuple = tuple(
        settlement for settlement in settlements
        if _known_by(settlement.knowledge_at, decision_time)
    )
    for action in visible:
        for side in ("LONG", "SHORT"):
            results[(action.action_id, side)] = _distribution_for_side(
                holding_tuple, action, side, settlement_tuple, window
            )
    for action_id in conflicts:
        for side in ("LONG", "SHORT"):
            results[(action_id, side)] = _unknown_result(side, action_id, ZERO, ("conflicting_action_revision",))
    return DistributionBook(
        results=results,
        visible_action_ids=tuple(sorted(action.action_id for action in visible)),
        hidden_action_ids=tuple(sorted(hidden_ids)),
    )


def calculate_distribution(
    holdings: Iterable[Holding],
    action: DistributionAction,
    settlements: Iterable[Settlement] = (),
    *,
    decision_time: Optional[datetime] = None,
    window: Optional[TimeWindow] = None,
) -> DistributionBook:
    """Convenience wrapper for one action, preserving the typed book interface."""

    return calculate_distributions(
        holdings, (action,), settlements, decision_time=decision_time, window=window
    )


def calculate_borrow(
    interval: BorrowInterval,
    *,
    settlements: Iterable[BorrowSettlement] = (),
    window: Optional[TimeWindow] = None,
    decision_time: Optional[datetime] = None,
    previous_exact: object = ZERO,
    previous_rounded_target: object = ZERO,
    prior_settled: object = ZERO,
) -> BorrowResult:
    """Calculate ACT/day-count borrow accrual with cumulative cent posting.

    Calendar days are dates in ``[start.date(), end.date())``; weekends and holidays
    therefore count.  ``previous_exact`` and ``previous_rounded_target`` allow a
    billing period to continue across a reporting-window boundary without resetting
    its rounding accumulator.
    """

    days = max((interval.end.date() - interval.start.date()).days, 0)
    notional_days = interval.quantity * interval.base_price * Decimal(days)
    if interval.quantity == ZERO or days == 0:
        return BorrowResult(
            "known", interval.interval_id, days, notional_days, ZERO, ZERO, ZERO,
            tuple(ZERO for _ in range(days)), tuple(ZERO for _ in range(days)),
            settled=ZERO, cash_delta=ZERO, economic_expense=ZERO,
            payable=ZERO, refund_receivable=ZERO,
        )
    if decision_time is not None and not _known_by(interval.knowledge_at, decision_time):
        return BorrowResult("unknown", interval.interval_id, days, notional_days, None, None, None, missing_rate_days=days, unknown_reasons=("rate_not_known_at_decision",))
    if interval.annual_rate is None:
        return BorrowResult("unknown", interval.interval_id, days, notional_days, None, None, None, missing_rate_days=days, unknown_reasons=("missing_borrow_rate",))
    if not interval.currency:
        return BorrowResult("unknown", interval.interval_id, days, notional_days, None, None, None, missing_rate_days=days, unknown_reasons=("missing_currency",))
    daily = interval.quantity * interval.base_price * interval.annual_rate / interval.denominator
    daily_exact = tuple(daily for _ in range(days))
    exact_fee = sum(daily_exact, ZERO)
    prior_exact = decimal(previous_exact)
    prior_rounded = round_cents(previous_rounded_target)
    postings: List[Decimal] = []
    cumulative = prior_exact
    prior_target = prior_rounded
    for day_fee in daily_exact:
        cumulative += day_fee
        target = round_cents(cumulative)
        postings.append(target - prior_target)
        prior_target = target
    rounded_target = round_cents(prior_exact + exact_fee)
    relevant = [settlement for settlement in settlements if settlement.charge_id == interval.interval_id]
    if decision_time is not None:
        relevant = [
            settlement for settlement in relevant
            if _known_by(settlement.knowledge_at, decision_time)
        ]
    if window is not None:
        relevant = [settlement for settlement in relevant if window.contains(settlement.occurred_at)]
    deduped, settlement_conflicts = _dedupe_borrow_settlements(relevant)
    if settlement_conflicts:
        return BorrowResult(
            "unknown", interval.interval_id, days, notional_days, None, None, None,
            missing_rate_days=0, unknown_reasons=("conflicting_borrow_settlement",),
        )
    if any(settlement.amount is None for settlement in deduped):
        return BorrowResult(
            "unknown", interval.interval_id, days, notional_days, None, None, None,
            unknown_reasons=("missing_borrow_settlement_amount",),
        )
    if any(settlement.currency is None for settlement in deduped):
        return BorrowResult(
            "unknown", interval.interval_id, days, notional_days, None, None, None,
            unknown_reasons=("missing_borrow_settlement_currency",),
        )
    if any(settlement.currency != interval.currency for settlement in deduped):
        return BorrowResult(
            "unknown", interval.interval_id, days, notional_days, None, None, None,
            unknown_reasons=("settlement_currency_mismatch",),
        )
    current_settlement = sum(
        (settlement.amount if settlement.kind == "payment" else -settlement.amount for settlement in deduped),
        ZERO,
    )
    net_settlement = decimal(prior_settled) + current_settlement
    opening_borrow = ZERO if window is None else decimal(window.opening_borrow_payables.get(interval.interval_id, ZERO))
    opening_refund = ZERO if window is None else decimal(window.opening_refund_receivables.get((interval.interval_id, "SHORT"), ZERO))
    previous_target = round_cents(previous_rounded_target)
    target_delta = rounded_target - previous_target
    if window is None:
        net_balance = rounded_target - net_settlement
        payable = max(net_balance, ZERO)
        refund = max(-net_balance, ZERO)
    else:
        net_balance = opening_borrow - opening_refund + target_delta - current_settlement
        payable = max(net_balance, ZERO)
        refund = max(-net_balance, ZERO)
    return BorrowResult(
        status="known", interval_id=interval.interval_id, calendar_days=days,
        notional_days=notional_days, exact_fee=exact_fee,
        rounded_target=rounded_target, posted_fee=sum(postings, ZERO),
        daily_exact=daily_exact, cumulative_postings=tuple(postings),
        settled=net_settlement, cash_delta=-current_settlement,
        economic_expense=target_delta, payable=payable,
        refund_receivable=refund,
        included_settlements=tuple(sorted(settlement.payment_id for settlement in deduped)),
    )
