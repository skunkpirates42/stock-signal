"""Market-regime classification.

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

BULL = "BULL"
BEAR = "BEAR"
CHOPPY = "CHOPPY"


def _index_direction(ind: dict) -> str:
    """'up' | 'down' | 'flat' for one index's indicator dict."""
    close, sma20, sma50 = ind["close"], ind["sma20"], ind["sma50"]
    if close > sma20 > sma50:
        return "up"
    if close < sma20 < sma50:
        return "down"
    return "flat"


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
