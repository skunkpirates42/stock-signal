"""Open/close logic and outcome detection.

Given an open position and a price bar, decide whether the bar's range triggered the stop
or the target, and classify the outcome. This is what `trades/tracker.py` does in the spec.

Same-bar rule: if a single bar's range spans BOTH the stop and the target (we can't see
intrabar order from OHLC alone), we conservatively assume the STOP filled first. This
avoids overstating win rate during validation.
"""


def check_exit(position: dict, bar) -> dict:
    """Return an exit dict {exit_price, outcome, reason} if the bar triggers stop/target,
    else None. `bar` must expose `high` and `low` (a pandas row or a dict)."""
    high = float(bar["high"])
    low = float(bar["low"])
    stop = position["stop"]
    target = position["target"]

    if position["direction"] == "LONG":
        hit_stop = low <= stop
        hit_target = high >= target
        if hit_stop:  # conservative: stop wins ties
            return {"exit_price": stop, "outcome": "LOSS", "reason": "stop"}
        if hit_target:
            return {"exit_price": target, "outcome": "WIN", "reason": "target"}
    else:  # SHORT
        hit_stop = high >= stop
        hit_target = low <= target
        if hit_stop:
            return {"exit_price": stop, "outcome": "LOSS", "reason": "stop"}
        if hit_target:
            return {"exit_price": target, "outcome": "WIN", "reason": "target"}

    return None
