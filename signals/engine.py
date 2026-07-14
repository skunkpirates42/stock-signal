"""Rule-based signal engine.

This is the heart of the system and is intentionally pure: it takes a dict of indicator
values and returns a signal dict. No data fetching, no I/O, no LLM. That keeps the trading
decision transparent, debuggable, and unit-testable, per the design notes in CLAUDE.md.

Six indicators cast directional votes. Volume ratio is NOT a directional vote — it is a
confirmation modifier that nudges the final confidence up or down.
"""

import json

import config

BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"


def vote(ind: dict) -> dict:
    """Return a per-indicator directional vote ('bull' | 'bear' | 'neutral').

    Conditions come straight from the CLAUDE.md indicator table.
    """
    votes = {}

    # RSI(14): oversold -> bullish, overbought -> bearish.
    if ind["rsi"] < config.RSI_BULL:
        votes["rsi"] = BULL
    elif ind["rsi"] > config.RSI_BEAR:
        votes["rsi"] = BEAR
    else:
        votes["rsi"] = NEUTRAL

    # Price vs SMA20.
    votes["price_vs_sma20"] = BULL if ind["close"] > ind["sma20"] else BEAR

    # SMA20 vs SMA50 (trend).
    votes["sma20_vs_sma50"] = BULL if ind["sma20"] > ind["sma50"] else BEAR

    # Price vs VWAP.
    votes["price_vs_vwap"] = BULL if ind["close"] > ind["vwap"] else BEAR

    # MACD line sign.
    votes["macd"] = BULL if ind["macd"] > 0 else BEAR

    # Bollinger Band position (%B): near lower band -> bullish, near upper -> bearish.
    if ind["bb_pct"] < config.BB_NEAR_LOWER:
        votes["bb"] = BULL
    elif ind["bb_pct"] > config.BB_NEAR_UPPER:
        votes["bb"] = BEAR
    else:
        votes["bb"] = NEUTRAL

    return votes


def _entry_stop_target(direction: str, entry: float, atr: float):
    """Compute stop/target/rr from ATR multipliers for a given direction."""
    stop_dist = atr * config.ATR_STOP_MULT
    target_dist = atr * config.ATR_TARGET_MULT
    if direction == "LONG":
        stop = entry - stop_dist
        target = entry + target_dist
    else:  # SHORT
        stop = entry + stop_dist
        target = entry - target_dist
    rr = abs(target - entry) / abs(entry - stop) if stop != entry else 0.0
    return stop, target, rr


def generate_signal(ticker: str, ind: dict) -> dict:
    """Turn indicator values into a full signal dict.

    Returns keys matching the `signals` table in CLAUDE.md:
    ticker, direction, confidence, entry, stop, target, rr, indicators_json
    (plus `votes` and `indicators` for human-readable output).
    """
    votes = vote(ind)
    n_directional = 6  # the 6 voting indicators (volume is a modifier, not a vote)
    bull = sum(1 for v in votes.values() if v == BULL)
    bear = sum(1 for v in votes.values() if v == BEAR)

    agreement = max(bull, bear) / n_directional
    if bull > bear:
        direction = "LONG"
    elif bear > bull:
        direction = "SHORT"
    else:
        direction = "WAIT"

    # Below the agreement threshold -> stand aside.
    if agreement < config.CONFIDENCE_THRESHOLD:
        direction = "WAIT"

    # Confidence = agreement, nudged by the volume confirmation modifier.
    confidence = agreement
    vr = ind["volume_ratio"]
    if vr > config.VOLUME_CONFIRM:
        confidence += config.VOLUME_CONFIDENCE_DELTA
    elif vr < config.VOLUME_WEAKEN:
        confidence -= config.VOLUME_CONFIDENCE_DELTA
    confidence = max(0.0, min(1.0, confidence))

    entry = ind["close"]
    stop = target = rr = None
    if direction != "WAIT":
        stop, target, rr = _entry_stop_target(direction, entry, ind["atr"])
        # Enforce the minimum reward:risk; downgrade to WAIT if it isn't met.
        # The 1e-9 tolerance avoids rejecting a clean 2:1 setup whose rr lands at
        # 1.9999999999 from floating-point subtraction of prices.
        if rr is None or rr < config.MIN_RR - 1e-9:
            direction = "WAIT"
            stop = target = rr = None

    signal = {
        "ticker": ticker,
        "direction": direction,
        "confidence": round(confidence, 4),
        "entry": round(entry, 4) if entry is not None else None,
        "stop": round(stop, 4) if stop is not None else None,
        "target": round(target, 4) if target is not None else None,
        "rr": round(rr, 4) if rr is not None else None,
        "votes": votes,
        "vote_tally": {"bull": bull, "bear": bear, "neutral": n_directional - bull - bear},
        "indicators": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in ind.items()},
    }
    signal["indicators_json"] = json.dumps(
        {"votes": votes, "values": ind, "tally": signal["vote_tally"]}
    )
    return signal
