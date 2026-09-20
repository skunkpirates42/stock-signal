"""Market-regime classification and the causal regime eligibility gate.

Tags the prevailing market regime from the index ETFs (SPY + QQQ) so signals/trades can be
analyzed by regime — CLAUDE.md notes trending vs choppy markets behave very differently.

Classification is transparent and uses only indicators we already compute:
- An index is trending UP when close > SMA20 > SMA50 (price leads a rising fast-over-slow),
  DOWN when close < SMA20 < SMA50, otherwise FLAT (range-bound / mixed).
- Regime = BULL when both SPY and QQQ trend up, BEAR when both trend down, else CHOPPY
  (they disagree or at least one is range-bound). Requiring both indices to agree keeps the
  trend buckets meaningful and dumps ambiguous tape into CHOPPY.

If QQQ isn't available, SPY alone decides (UP→BULL, DOWN→BEAR, FLAT→CHOPPY).
"""

import math

BULL = "BULL"
BEAR = "BEAR"
CHOPPY = "CHOPPY"
UNKNOWN = "UNKNOWN"


class RegimeContext(dict):
    """Serializable context for a decision-time regime.

    ``classify`` intentionally keeps its historical CHOPPY return value for callers
    that only need a display bucket.  Eligibility code must use this context so a
    missing or stale SPY observation cannot be mistaken for a known choppy market.
    """

    def __init__(self, regime, *, known, reason, spy_available=True, qqq_available=True):
        super().__init__(regime=regime, known=bool(known), reason=reason,
                         spy_available=bool(spy_available), qqq_available=bool(qqq_available))

    @property
    def regime(self):
        return self["regime"]

    @property
    def known(self):
        return self["known"]

    @property
    def reason(self):
        return self["reason"]


def _index_direction(ind: dict) -> str:
    """'up' | 'down' | 'flat' for one index's indicator dict."""
    close, sma20, sma50 = ind["close"], ind["sma20"], ind["sma50"]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (close, sma20, sma50)):
        raise ValueError("index indicators are incomplete")
    if close > sma20 > sma50:
        return "up"
    if close < sma20 < sma50:
        return "down"
    return "flat"


def classify_context(spy_ind: dict, qqq_ind: dict = None, *, stale=False,
                     qqq_stale=False) -> RegimeContext:
    """Classify decision-time context while retaining missingness and freshness.

    SPY is the required benchmark.  QQQ remains an optional confirming index to
    preserve the existing classifier's SPY fallback, but its absence is recorded
    in the context.  A stale or missing SPY is always UNKNOWN and is ineligible for
    a regime-gated candidate.
    """
    if stale:
        return RegimeContext(UNKNOWN, known=False, reason="stale_spy",
                             spy_available=spy_ind is not None, qqq_available=qqq_ind is not None)
    if spy_ind is None:
        return RegimeContext(UNKNOWN, known=False, reason="missing_spy",
                             spy_available=False, qqq_available=qqq_ind is not None)
    try:
        spy_dir = _index_direction(spy_ind)
    except (KeyError, TypeError, ValueError):
        return RegimeContext(UNKNOWN, known=False, reason="invalid_spy",
                             spy_available=True, qqq_available=qqq_ind is not None)
    if qqq_stale:
        qqq_ind = None
    if qqq_ind is None:
        regime = {"up": BULL, "down": BEAR}.get(spy_dir, CHOPPY)
        return RegimeContext(regime, known=True, reason="qqq_unavailable" if qqq_stale else "spy_only",
                             spy_available=True, qqq_available=False)
    try:
        qqq_dir = _index_direction(qqq_ind)
    except (KeyError, TypeError, ValueError):
        regime = {"up": BULL, "down": BEAR}.get(spy_dir, CHOPPY)
        return RegimeContext(regime, known=True, reason="invalid_qqq_spy_only",
                             spy_available=True, qqq_available=True)
    if spy_dir == qqq_dir == "up":
        regime = BULL
    elif spy_dir == qqq_dir == "down":
        regime = BEAR
    else:
        regime = CHOPPY
    return RegimeContext(regime, known=True, reason="aligned" if regime != CHOPPY else "disagreement_or_flat",
                         spy_available=True, qqq_available=True)


def regime_eligibility(direction: str, context) -> dict:
    """Return a deterministic regime gate decision and persisted reason."""
    if context is None:
        context = RegimeContext(UNKNOWN, known=False, reason="missing_context",
                                spy_available=False, qqq_available=False)
    elif not isinstance(context, dict):
        context = RegimeContext(getattr(context, "regime", UNKNOWN),
                                known=getattr(context, "known", False),
                                reason=getattr(context, "reason", "unknown_context"),
                                spy_available=getattr(context, "spy_available", False),
                                qqq_available=getattr(context, "qqq_available", False))
    if direction not in ("LONG", "SHORT"):
        return {"accepted": False, "reason": "invalid_direction", "direction": direction,
                "regime": context.get("regime", UNKNOWN), "context": dict(context)}
    if not context.get("known") or context.get("regime") == UNKNOWN:
        return {"accepted": False, "reason": "unknown_context", "direction": direction,
                "regime": context.get("regime", UNKNOWN), "context": dict(context)}
    regime = context.get("regime")
    if regime == CHOPPY:
        return {"accepted": False, "reason": "choppy_regime", "direction": direction,
                "regime": regime, "context": dict(context)}
    expected = BULL if direction == "LONG" else BEAR
    if regime != expected:
        return {"accepted": False, "reason": "direction_regime_mismatch", "direction": direction,
                "regime": regime, "expected": expected, "context": dict(context)}
    return {"accepted": True, "reason": "regime_aligned", "direction": direction,
            "regime": regime, "context": dict(context)}


def classify(spy_ind: dict, qqq_ind: dict = None) -> str:
    """Return BULL / BEAR / CHOPPY from SPY (and optionally QQQ) indicator values."""
    if spy_ind is None:
        return CHOPPY
    spy_dir = _index_direction(spy_ind)
    if qqq_ind is None:
        return {"up": BULL, "down": BEAR}.get(spy_dir, CHOPPY)

    qqq_dir = _index_direction(qqq_ind)
    if spy_dir == qqq_dir == "up":
        return BULL
    if spy_dir == qqq_dir == "down":
        return BEAR
    return CHOPPY
