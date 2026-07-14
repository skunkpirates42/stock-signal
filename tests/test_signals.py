"""Unit tests for the rule-based voting engine.

These pin the voting math with hand-built indicator dicts — no data fetch, no network,
no pandas-ta — so they're fast and stable.
"""

import config
from signals.engine import generate_signal, vote


def _indicators(**overrides):
    """A neutral-ish baseline indicator dict; override keys per test."""
    base = {
        "close": 100.0,
        "rsi": 50.0,
        "sma20": 100.0,
        "sma50": 100.0,
        "vwap": 100.0,
        "macd": 0.0,
        "bb_pct": 0.5,
        "volume_ratio": 1.0,
        "atr": 2.0,
    }
    base.update(overrides)
    return base


ALL_BULL = _indicators(
    rsi=30.0, close=110.0, sma20=100.0, sma50=90.0, vwap=105.0, macd=1.0, bb_pct=0.10
)
ALL_BEAR = _indicators(
    rsi=70.0, close=90.0, sma20=100.0, sma50=110.0, vwap=95.0, macd=-1.0, bb_pct=0.90
)
# 3 bull (rsi/sma20/sma50-trend) vs 3 bear (vwap/macd/bb) -> 50% agreement.
SPLIT = _indicators(
    rsi=30.0, close=110.0, sma20=100.0, sma50=90.0, vwap=120.0, macd=-1.0, bb_pct=0.90
)


def test_all_bullish_is_long():
    sig = generate_signal("TEST", ALL_BULL)
    assert sig["direction"] == "LONG"
    assert sig["vote_tally"]["bull"] == 6
    assert sig["entry"] == 110.0
    assert sig["stop"] < sig["entry"] < sig["target"]
    assert sig["rr"] == 2.0


def test_all_bearish_is_short():
    sig = generate_signal("TEST", ALL_BEAR)
    assert sig["direction"] == "SHORT"
    assert sig["vote_tally"]["bear"] == 6
    assert sig["target"] < sig["entry"] < sig["stop"]
    assert sig["rr"] == 2.0


def test_split_vote_is_wait():
    sig = generate_signal("TEST", SPLIT)
    assert sig["direction"] == "WAIT"
    assert sig["stop"] is None and sig["target"] is None and sig["rr"] is None


def test_low_rr_downgrades_to_wait(monkeypatch):
    # Make target distance < 2x stop distance so R:R falls below MIN_RR (2.0).
    monkeypatch.setattr(config, "ATR_TARGET_MULT", 2.0)
    monkeypatch.setattr(config, "ATR_STOP_MULT", 1.5)
    sig = generate_signal("TEST", ALL_BULL)
    assert sig["direction"] == "WAIT"  # would be LONG, but R:R ~1.33 < 2.0


def test_clean_2to1_survives_fp_rounding():
    # Regression: a fractional ATR makes rr land at ~1.9999999999 from price
    # subtraction; the MIN_RR check must not reject this valid 2:1 setup.
    sig = generate_signal("TEST", _indicators(**{**ALL_BULL, "atr": 0.564559744428803}))
    assert sig["direction"] == "LONG"
    assert sig["rr"] == 2.0


def test_volume_modifier_boosts_and_dampens():
    strong = generate_signal("TEST", _indicators(**{**ALL_BULL, "volume_ratio": 2.0}))
    weak = generate_signal("TEST", _indicators(**{**ALL_BULL, "volume_ratio": 0.5}))
    assert strong["confidence"] > weak["confidence"]


def test_vote_neutral_bands():
    v = vote(_indicators(rsi=50.0, bb_pct=0.5))
    assert v["rsi"] == "neutral"
    assert v["bb"] == "neutral"
