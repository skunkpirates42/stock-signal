"""Unit tests for the paper broker and exit tracker.

No data fetch / no network — positions and bars are hand-built.
"""

import config
from trades.executor import PaperBroker
from trades.tracker import check_exit


def _long_signal(entry=100.0, stop=98.0, target=104.0):
    return {
        "ticker": "TEST",
        "direction": "LONG",
        "entry": entry,
        "stop": stop,
        "target": target,
    }


def test_position_sizing_is_10pct_of_capital():
    b = PaperBroker(starting_capital=100_000.0, position_pct=0.10)
    pos = b.open_position(_long_signal(entry=100.0), entry_bar=0)
    assert pos["shares"] == 100  # floor(10_000 / 100)


def test_one_position_per_ticker():
    b = PaperBroker(starting_capital=100_000.0)
    assert b.open_position(_long_signal(), entry_bar=0) is not None
    assert b.open_position(_long_signal(), entry_bar=1) is None  # already open


def test_wait_signal_does_not_open():
    b = PaperBroker()
    sig = {"ticker": "TEST", "direction": "WAIT", "entry": 100.0, "stop": None, "target": None}
    assert b.open_position(sig, entry_bar=0) is None


def test_long_target_hit_is_win_and_profit():
    b = PaperBroker(starting_capital=100_000.0)
    b.open_position(_long_signal(entry=100.0, stop=98.0, target=104.0), entry_bar=0)
    exit_ = check_exit(b.open_positions["TEST"], {"high": 104.5, "low": 101.0})
    assert exit_["outcome"] == "WIN" and exit_["exit_price"] == 104.0
    trade = b.close_position("TEST", exit_["exit_price"], exit_["outcome"], exit_bar=5)
    assert trade["pnl"] > 0
    assert trade["bars_held"] == 5
    assert b.capital == 100_000.0 + trade["pnl"]


def test_long_stop_hit_is_loss():
    b = PaperBroker(starting_capital=100_000.0)
    b.open_position(_long_signal(entry=100.0, stop=98.0, target=104.0), entry_bar=0)
    exit_ = check_exit(b.open_positions["TEST"], {"high": 101.0, "low": 97.5})
    assert exit_["outcome"] == "LOSS" and exit_["exit_price"] == 98.0
    trade = b.close_position("TEST", exit_["exit_price"], exit_["outcome"], exit_bar=3)
    assert trade["pnl"] < 0


def test_short_target_hit_is_win():
    b = PaperBroker()
    sig = {"ticker": "TEST", "direction": "SHORT", "entry": 100.0, "stop": 102.0, "target": 96.0}
    b.open_position(sig, entry_bar=0)
    exit_ = check_exit(b.open_positions["TEST"], {"high": 100.5, "low": 95.5})
    assert exit_["outcome"] == "WIN" and exit_["exit_price"] == 96.0


def test_same_bar_stop_and_target_assumes_stop_first():
    b = PaperBroker()
    b.open_position(_long_signal(entry=100.0, stop=98.0, target=104.0), entry_bar=0)
    # Bar range spans BOTH levels -> conservative LOSS.
    exit_ = check_exit(b.open_positions["TEST"], {"high": 105.0, "low": 97.0})
    assert exit_["outcome"] == "LOSS" and exit_["reason"] == "stop"


def test_no_exit_when_bar_inside_range():
    b = PaperBroker()
    b.open_position(_long_signal(entry=100.0, stop=98.0, target=104.0), entry_bar=0)
    assert check_exit(b.open_positions["TEST"], {"high": 103.0, "low": 99.0}) is None
