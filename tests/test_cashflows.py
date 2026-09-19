"""Offline known-answer fixtures for the pure accounting calculations."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trades.cashflows import (
    BorrowInterval,
    BorrowSettlement,
    DistributionAction,
    Holding,
    Settlement,
    TimeWindow,
    calculate_borrow,
    calculate_distribution,
    calculate_distributions,
    round_cents,
)


UTC = timezone.utc


def at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 6, day, hour, tzinfo=UTC)


def long_lot(quantity="100", *, entry=5, exit=None):
    return Holding("L1", "TEST", "LONG", Decimal(quantity), at(entry), None if exit is None else at(exit))


def short_lot(quantity="100", *, entry=5, exit=None):
    return Holding("S1", "TEST", "SHORT", Decimal(quantity), at(entry), None if exit is None else at(exit))


def action(rate="1.00", *, ex_hour=4, revision="A", supersedes=None, knowledge=1):
    return DistributionAction(
        "D1", "TEST", at(8, ex_hour), None if rate is None else Decimal(rate),
        currency="USD",
        revision_id=revision, supersedes_revision=supersedes,
        knowledge_at=at(knowledge),
    )


def result(book, side):
    return book.results[("D1", side)]


def test_long_accrual_and_payment_are_separate():
    accrued = result(calculate_distribution((long_lot(),), action()), "LONG")
    assert accrued.status == "known"
    assert accrued.exact_target == Decimal("100.00")
    assert accrued.target == Decimal("100.00")
    assert accrued.economic_income == Decimal("100.00")
    assert accrued.receivable == Decimal("100.00")
    assert accrued.cash_delta == Decimal("0")

    paid = result(
        calculate_distribution(
            (long_lot(),), action(),
            (Settlement("P1", "D1", Decimal("100"), at(15), currency="USD"),),
        ),
        "LONG",
    )
    assert paid.cash_delta == Decimal("100")
    assert paid.receivable == Decimal("0")
    assert paid.economic_income == Decimal("100")


def test_short_distribution_has_opposite_sign_and_payment_is_not_second_expense():
    accrued = result(calculate_distribution((short_lot(),), action()), "SHORT")
    assert accrued.payable == Decimal("100")
    assert accrued.economic_income == Decimal("-100")
    assert accrued.cash_delta == Decimal("0")
    paid = result(
        calculate_distribution(
            (short_lot(),), action(),
            (Settlement("P1", "D1", Decimal("100"), at(15), currency="USD"),),
        ),
        "SHORT",
    )
    assert paid.cash_delta == Decimal("-100")
    assert paid.payable == Decimal("0")
    assert paid.economic_income == Decimal("-100")


def test_distribution_settlement_must_be_scoped_to_one_side():
    holdings = (long_lot(), short_lot())
    unscoped = Settlement("P1", "D1", Decimal("100"), at(15), currency="USD")
    ambiguous = calculate_distribution(holdings, action(), (unscoped,))
    assert ambiguous.results[("D1", "LONG")].status == "unknown"
    assert ambiguous.results[("D1", "SHORT")].status == "unknown"

    long_payment = Settlement("P1", "D1", Decimal("100"), at(15), side="LONG", currency="USD")
    scoped = calculate_distribution(holdings, action(), (long_payment,))
    assert scoped.results[("D1", "LONG")].receivable == Decimal("0")
    assert scoped.results[("D1", "SHORT")].payable == Decimal("100")


def test_pre_ex_close_and_exact_ex_entry_boundary_are_not_entitled():
    pre_close = result(calculate_distribution((long_lot(exit=7),), action()), "LONG")
    assert pre_close.qualified_quantity == Decimal("0")
    exact_entry = Holding("L2", "TEST", "LONG", Decimal("100"), at(8, 4))
    on_cutoff = result(calculate_distribution((exact_entry,), action()), "LONG")
    assert on_cutoff.target == Decimal("0")
    exact_exit = Holding("L3", "TEST", "LONG", Decimal("100"), at(5), at(8, 4))
    assert result(calculate_distribution((exact_exit,), action()), "LONG").target == Decimal("100")


def test_close_after_ex_date_retains_full_entitlement_and_window_is_end_inclusive():
    lot = long_lot(exit=10)
    payment = Settlement("P1", "D1", Decimal("100"), at(15), currency="USD")
    partial_window = TimeWindow(at(8), at(12))
    closed = result(calculate_distribution((lot,), action(), (payment,), window=partial_window), "LONG")
    assert closed.target == Decimal("100")
    assert closed.receivable == Decimal("100")
    at_end = result(
            calculate_distribution((lot,), action(), (Settlement("P2", "D1", Decimal("100"), at(12), currency="USD"),), window=partial_window),
        "LONG",
    )
    assert at_end.receivable == Decimal("0")


def test_duplicate_and_corrected_actions_are_idempotent():
    duplicate = calculate_distributions((long_lot(),), (action(), action()))
    assert result(duplicate, "LONG").target == Decimal("100")

    revised = calculate_distributions(
        (long_lot(),),
        (action(), action("1.20", revision="B", supersedes="A")),
        (Settlement("P1", "D1", Decimal("100"), at(15), currency="USD"),),
    )
    corrected = result(revised, "LONG")
    assert corrected.target == Decimal("120")
    assert corrected.receivable == Decimal("20")
    assert corrected.cash_delta == Decimal("100")

    downward = calculate_distributions(
        (long_lot(),),
        (action(), action("0.80", revision="B", supersedes="A")),
        (Settlement("P1", "D1", Decimal("100"), at(15), currency="USD"),),
    )
    assert result(downward, "LONG").repayment_liability == Decimal("20")


def test_conflicting_unordered_revision_is_unknown():
    book = calculate_distributions((long_lot(),), (action(), action("1.20", revision="B")))
    assert book.results[("D1", "LONG")].status == "unknown"


def test_decimal_rounding_and_largest_remainder_allocation():
    assert round_cents("1.005") == Decimal("1.01")
    first = Holding("A", "TEST", "LONG", Decimal("1"), at(5))
    second = Holding("B", "TEST", "LONG", Decimal("1"), at(5))
    book = calculate_distribution(
        (first, second),
        DistributionAction("D1", "TEST", at(8, 4), Decimal("0.005"), currency="USD"),
    )
    long_result = result(book, "LONG")
    assert long_result.target == Decimal("0.01")
    assert long_result.lot_allocations == {"A": Decimal("0.01"), "B": Decimal("0.00")}


def test_zero_position_is_known_even_when_rate_is_missing():
    empty = result(
        calculate_distribution(
            (Holding("zero", "TEST", "LONG", Decimal("0"), at(5)),),
            action(None),
        ),
        "LONG",
    )
    assert empty.status == "known" and empty.target == Decimal("0")
    missing = result(calculate_distribution((long_lot(),), action(None)), "LONG")
    assert missing.status == "unknown"
    assert "missing_distribution_rate" in missing.unknown_reasons


def test_borrow_counts_weekend_and_rounds_cumulatively():
    interval = BorrowInterval("B1", Decimal("100"), Decimal("50"), Decimal("0.36"), at(5), at(8), currency="USD")
    fee = calculate_borrow(interval)
    assert fee.calendar_days == 3
    assert fee.notional_days == Decimal("15000")
    assert fee.exact_fee == Decimal("15.00")
    assert fee.cumulative_postings == (Decimal("5.00"), Decimal("5.00"), Decimal("5.00"))

    tiny = BorrowInterval("B2", Decimal("1"), Decimal("1"), Decimal("1.44"), at(5), at(8), denominator=Decimal("360"), currency="USD")
    tiny_fee = calculate_borrow(tiny)
    assert tiny_fee.daily_exact == (Decimal("0.004"),) * 3
    assert tiny_fee.cumulative_postings == (Decimal("0.00"), Decimal("0.01"), Decimal("0.00"))
    assert tiny_fee.posted_fee == Decimal("0.01")


def test_borrow_payment_refund_and_revised_target_are_balanced():
    original = BorrowInterval("B1", Decimal("100"), Decimal("50"), Decimal("0.36"), at(5), at(8), currency="USD")
    payment = BorrowSettlement("P1", "B1", Decimal("15"), at(9), currency="USD")
    paid = calculate_borrow(original, settlements=(payment,))
    assert paid.payable == Decimal("0")
    assert paid.refund_receivable == Decimal("0")
    assert paid.cash_delta == Decimal("-15")

    revised = BorrowInterval("B1", Decimal("100"), Decimal("50"), Decimal("0.24"), at(5), at(8), currency="USD")
    corrected = calculate_borrow(revised, previous_rounded_target=Decimal("15"), prior_settled=Decimal("15"))
    assert corrected.rounded_target == Decimal("10")
    assert corrected.refund_receivable == Decimal("5")
    refund = BorrowSettlement("R1", "B1", Decimal("5"), at(10), kind="refund", currency="USD")
    settled_correction = calculate_borrow(revised, settlements=(refund,), previous_rounded_target=Decimal("15"), prior_settled=Decimal("15"))
    assert settled_correction.refund_receivable == Decimal("0")
    assert settled_correction.cash_delta == Decimal("5")


def test_continuation_opening_receivable_payment_has_no_new_income():
    window = TimeWindow(
        at(12), at(16),
        opening_receivables={("D1", "LONG"): Decimal("100")},
    )
    inherited_action = action()
    inherited = Holding("old", "TEST", "LONG", Decimal("0"), at(5))
    payment = Settlement("P1", "D1", Decimal("100"), at(15), side="LONG", currency="USD")
    result_ = result(calculate_distribution((inherited,), inherited_action, (payment,), window=window), "LONG")
    assert result_.economic_income == Decimal("0")
    assert result_.receivable == Decimal("0")
    assert result_.cash_delta == Decimal("100")


def test_borrow_continuation_opening_payable_payment_has_no_new_expense():
    window = TimeWindow(
        at(8), at(16),
        opening_borrow_payables={"B1": Decimal("15")},
    )
    interval = BorrowInterval("B1", Decimal("100"), Decimal("50"), Decimal("0"), at(8), at(9), currency="USD")
    payment = BorrowSettlement("P1", "B1", Decimal("15"), at(10), currency="USD")
    result_ = calculate_borrow(interval, settlements=(payment,), window=window)
    assert result_.economic_expense == Decimal("0")
    assert result_.payable == Decimal("0")
    assert result_.cash_delta == Decimal("-15")


def test_causal_borrow_hides_late_payment_from_decision_state():
    interval = BorrowInterval(
        "B1", Decimal("100"), Decimal("50"), Decimal("0.36"), at(5), at(8),
        currency="USD", knowledge_at=at(8),
    )
    late_payment = BorrowSettlement(
        "P1", "B1", Decimal("15"), at(9), currency="USD", knowledge_at=at(12),
    )
    causal = calculate_borrow(interval, settlements=(late_payment,), decision_time=at(10))
    assert causal.payable == Decimal("15")
    assert causal.cash_delta == Decimal("0")
    eventual = calculate_borrow(interval, settlements=(late_payment,))
    assert eventual.payable == Decimal("0")
    assert eventual.cash_delta == Decimal("-15")


def test_continuation_revision_carries_prior_target_and_settlement_to_repayment_liability():
    window = TimeWindow(
        at(12), at(16),
        opening_targets={("D1", "LONG"): Decimal("100")},
        opening_settled={("D1", "LONG"): Decimal("100")},
        opening_receivables={("D1", "LONG"): Decimal("0")},
        opening_repayment_liabilities={("D1", "LONG"): Decimal("0")},
    )
    revised = action("0.80", revision="B", supersedes="A")
    revised_result = result(
        calculate_distribution((long_lot(exit=10),), revised, window=window),
        "LONG",
    )
    assert revised_result.target == Decimal("80.00")
    assert revised_result.settled == Decimal("100")
    assert revised_result.receivable == Decimal("0")
    assert revised_result.repayment_liability == Decimal("20.00")
    assert revised_result.economic_income == Decimal("0")


def test_float_amounts_are_rejected_and_currency_is_required():
    with pytest.raises(TypeError):
        round_cents(1.005)
    missing_currency = calculate_borrow(
        BorrowInterval("B1", Decimal("1"), Decimal("1"), Decimal("0.36"), at(5), at(6))
    )
    assert missing_currency.status == "unknown"
    assert "missing_currency" in missing_currency.unknown_reasons


def test_settlement_currency_mismatch_is_unknown_without_fx():
    distribution = result(
        calculate_distribution(
            (long_lot(),), action(),
            (Settlement("P1", "D1", Decimal("100"), at(15), currency="EUR"),),
        ),
        "LONG",
    )
    assert distribution.status == "unknown"
    assert "settlement_currency_mismatch" in distribution.unknown_reasons

    borrow = calculate_borrow(
        BorrowInterval("B1", Decimal("100"), Decimal("50"), Decimal("0.36"), at(5), at(8), currency="USD"),
        settlements=(BorrowSettlement("P1", "B1", Decimal("15"), at(9), currency="EUR"),),
    )
    assert borrow.status == "unknown"
    assert "settlement_currency_mismatch" in borrow.unknown_reasons


def test_missing_borrow_rate_is_unknown_but_zero_exposure_is_known():
    missing = calculate_borrow(BorrowInterval("B1", Decimal("100"), Decimal("50"), None, at(5), at(8), currency="USD"))
    assert missing.status == "unknown"
    assert missing.notional_days == Decimal("15000")
    assert missing.missing_rate_days == 3
    zero = calculate_borrow(BorrowInterval("B2", Decimal("0"), Decimal("50"), None, at(5), at(8), currency="USD"))
    assert zero.status == "known" and zero.exact_fee == Decimal("0")


def test_late_correction_is_hidden_from_causal_decision_but_visible_eventually():
    original = action(knowledge=1)
    late = action("1.20", revision="B", supersedes="A", knowledge=20)
    causal = calculate_distributions((long_lot(),), (original, late), decision_time=at(10))
    assert result(causal, "LONG").target == Decimal("100")
    assert causal.hidden_action_ids == ()
    eventual = calculate_distributions((long_lot(),), (original, late))
    assert result(eventual, "LONG").target == Decimal("120")


def test_duplicate_settlement_is_idempotent_and_conflicting_id_is_unknown():
    p = Settlement("P1", "D1", Decimal("100"), at(15), currency="USD")
    paid = result(calculate_distribution((long_lot(),), action(), (p, p)), "LONG")
    assert paid.cash_delta == Decimal("100")
    conflict = result(
        calculate_distribution((long_lot(),), action(), (p, Settlement("P1", "D1", Decimal("90"), at(15), currency="USD"))),
        "LONG",
    )
    assert conflict.status == "unknown"


def test_unaware_datetimes_are_rejected():
    with pytest.raises(ValueError):
        DistributionAction("D", "TEST", datetime(2026, 6, 8), Decimal("1"))
