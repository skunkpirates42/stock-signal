"""Performance metrics.

Computes the validation metrics from CLAUDE.md over closed trades. `compute_metrics` is a
pure function over a list of trade dicts (ordered by close time) so it's unit-testable and
independent of the database; `load_closed_trades` pulls them from SQLite.

Metrics: win rate, avg win/loss, expectancy, profit factor, total P&L, max drawdown
(absolute + %), realized R-multiple (vs the theoretical 2:1), avg bars held, and a per-ticker
breakdown.

Signal-accuracy-by-regime (trending vs choppy) from CLAUDE.md is intentionally NOT here: it
needs each trade tagged with the prevailing market regime (e.g. SPY trend) at entry, which
isn't derivable from the trades table alone. See `by_regime` for the documented seam.
"""

import sqlite3

import config

CLOSED = ("WIN", "LOSS")


def _safe_mean(values):
    return sum(values) / len(values) if values else 0.0


def _r_multiple(trade) -> float:
    """Realized risk-multiple: P&L expressed in units of the trade's intended risk.

    A clean target hit = +2R (the theoretical 2:1), a clean stop = -1R. With real fills
    (slippage, gaps) these drift, which is exactly what 'R:R realized' is meant to surface.
    """
    risk_per_share = abs(trade["entry"] - trade["stop"])
    risk = risk_per_share * trade["shares"]
    return trade["pnl"] / risk if risk else 0.0


def _max_drawdown(closed, starting_capital):
    """Largest peak-to-trough decline of the realized-equity curve (trades in close order).

    Returns (abs_drawdown, pct_drawdown). pct is relative to the running peak.
    """
    equity = starting_capital
    peak = starting_capital
    max_abs = 0.0
    max_pct = 0.0
    for t in closed:
        equity += t["pnl"]
        peak = max(peak, equity)
        dd = peak - equity
        if dd > max_abs:
            max_abs = dd
        if peak > 0 and dd / peak > max_pct:
            max_pct = dd / peak
    return round(max_abs, 2), max_pct


def _breakdown(closed, key_fn):
    """Group closed trades by `key_fn(trade)` into {key: {n, wins, win_rate, pnl}}."""
    out = {}
    for t in closed:
        b = out.setdefault(key_fn(t), {"n": 0, "wins": 0, "pnl": 0.0})
        b["n"] += 1
        b["wins"] += 1 if t["outcome"] == "WIN" else 0
        b["pnl"] += t["pnl"]
    for b in out.values():
        b["win_rate"] = b["wins"] / b["n"] if b["n"] else 0.0
        b["pnl"] = round(b["pnl"], 2)
    return out


def compute_metrics(trades, starting_capital: float = None) -> dict:
    """Aggregate performance metrics over the closed trades in the given (close) order."""
    if starting_capital is None:
        starting_capital = config.STARTING_CAPITAL

    closed = [t for t in trades if t["outcome"] in CLOSED]
    n_open = sum(1 for t in trades if t["outcome"] == "OPEN")
    wins = [t for t in closed if t["outcome"] == "WIN"]
    losses = [t for t in closed if t["outcome"] == "LOSS"]
    n = len(closed)

    win_rate = len(wins) / n if n else 0.0
    avg_win = _safe_mean([t["pnl"] for t in wins])
    avg_loss = _safe_mean([t["pnl"] for t in losses])  # negative
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)  # positive magnitude
    profit_factor = (gross_profit / gross_loss) if gross_loss else float("inf")

    max_dd_abs, max_dd_pct = _max_drawdown(closed, starting_capital)

    return {
        "n_closed": n,
        "n_open": n_open,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": win_rate,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else None,
        "total_pnl": round(sum(t["pnl"] for t in closed), 2),
        "max_drawdown": max_dd_abs,
        "max_drawdown_pct": max_dd_pct,
        "avg_bars_held": round(_safe_mean([t["bars_held"] for t in closed]), 1),
        "avg_r_multiple": round(_safe_mean([_r_multiple(t) for t in closed]), 3),
        "avg_win_r": round(_safe_mean([_r_multiple(t) for t in wins]), 3),
        "avg_loss_r": round(_safe_mean([_r_multiple(t) for t in losses]), 3),
        "by_ticker": _breakdown(closed, lambda t: t["ticker"]),
        "by_regime": _breakdown(closed, lambda t: t.get("regime") or "UNKNOWN"),
        "ending_capital": round(starting_capital + sum(t["pnl"] for t in closed), 2),
        "starting_capital": starting_capital,
    }


def equity_curve(trades, starting_capital: float = None):
    """Realized-equity points over the closed trades (in the order given, i.e. close order).

    Returns a list of {"label", "equity", "pnl"} starting from `starting_capital`.
    """
    if starting_capital is None:
        starting_capital = config.STARTING_CAPITAL
    equity = starting_capital
    points = [{"label": "start", "equity": round(equity, 2), "pnl": 0.0}]
    for t in trades:
        if t["outcome"] not in CLOSED:
            continue
        equity += t["pnl"]
        label = (t.get("closed_at") or "")[:19] or t["ticker"]
        points.append({"label": label, "equity": round(equity, 2), "pnl": t["pnl"]})
    return points


def load_closed_trades(db_path: str = None, source: str = None):
    """Load all trades from SQLite as dicts, ordered by close time (then id).

    `source` optionally restricts to "live" or "backtest" rows; omitted, all rows load
    (unchanged from before the source column existed).
    """
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    # Join each trade to its signal to carry the market regime tagged at signal time.
    sql = """
        SELECT t.*, s.regime AS regime
          FROM trades t
          LEFT JOIN signals s ON t.signal_id = s.id
        """
    params = []
    if source:
        sql += " WHERE t.source = ?"
        params.append(source)
    sql += " ORDER BY t.closed_at IS NULL, t.closed_at, t.id"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def format_report(m: dict) -> str:
    """Render a metrics dict as a console report."""
    lines = []
    add = lines.append
    add("=" * 64)
    add("PERFORMANCE METRICS")
    add("=" * 64)
    if m["n_closed"] == 0:
        add("No closed trades yet.")
        return "\n".join(lines)

    add(f"Closed trades:    {m['n_closed']}   (still open: {m['n_open']})")
    add(f"Win rate:         {m['win_rate']:.1%}  ({m['n_wins']}W / {m['n_losses']}L)")
    add(f"Avg win / loss:   {m['avg_win']:+.2f} / {m['avg_loss']:+.2f}")
    add(f"Expectancy/trade: {m['expectancy']:+.2f}")
    pf = m["profit_factor"]
    add(f"Profit factor:    {pf if pf is not None else 'inf'}")
    add(f"Total P&L:        {m['total_pnl']:+.2f}")
    add(f"Max drawdown:     {m['max_drawdown']:.2f}  ({m['max_drawdown_pct']:.1%})")
    add(f"Avg bars held:    {m['avg_bars_held']}")
    add(f"Realized R-mult:  {m['avg_r_multiple']:+.3f}  "
        f"(wins {m['avg_win_r']:+.2f}R, losses {m['avg_loss_r']:+.2f}R; theoretical +2 / -1)")
    add(f"Ending capital:   {m['ending_capital']:,.2f}  "
        f"({(m['ending_capital'] / m['starting_capital'] - 1):+.2%})")

    add("-" * 64)
    add(f"{'BY REGIME':<10}{'N':>5}{'WIN%':>8}{'PNL':>12}")
    for regime, b in sorted(m["by_regime"].items(), key=lambda kv: kv[1]["pnl"], reverse=True):
        add(f"{regime:<10}{b['n']:>5}{b['win_rate']:>8.0%}{b['pnl']:>12.2f}")

    add("-" * 64)
    add(f"{'BY TICKER':<10}{'N':>5}{'WIN%':>8}{'PNL':>12}")
    for ticker, b in sorted(m["by_ticker"].items(), key=lambda kv: kv[1]["pnl"], reverse=True):
        add(f"{ticker:<10}{b['n']:>5}{b['win_rate']:>8.0%}{b['pnl']:>12.2f}")
    return "\n".join(lines)
