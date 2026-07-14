"""Tests for the SPY/QQQ market-regime classifier."""

from signals.regime import BEAR, BULL, CHOPPY, classify


def _ind(close, sma20, sma50):
    return {"close": close, "sma20": sma20, "sma50": sma50}


UP = _ind(110, 105, 100)     # close > sma20 > sma50
DOWN = _ind(90, 95, 100)     # close < sma20 < sma50
FLAT = _ind(100, 99, 100)    # not aligned either way


def test_both_up_is_bull():
    assert classify(UP, UP) == BULL


def test_both_down_is_bear():
    assert classify(DOWN, DOWN) == BEAR


def test_disagreement_is_choppy():
    assert classify(UP, DOWN) == CHOPPY
    assert classify(UP, FLAT) == CHOPPY
    assert classify(FLAT, FLAT) == CHOPPY


def test_spy_only_fallback():
    assert classify(UP, None) == BULL
    assert classify(DOWN, None) == BEAR
    assert classify(FLAT, None) == CHOPPY


def test_none_spy_is_choppy():
    assert classify(None, UP) == CHOPPY
