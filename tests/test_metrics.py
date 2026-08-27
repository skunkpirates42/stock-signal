"""Unit tests for the performance-metrics computations.

Hand-built closed trades with known outcomes pin the math.
"""

from analytics.metrics import compute_metrics, load_closed_trades
from db.logger import close_trade, init_db, log_trade_open


def _t(outcome, pnl, entry=100.0, stop=98.0, shares=10, bars_held=5, ticker="AAA",
       regime="BULL"):
    return {
        "outcome": outcome,
        "pnl": pnl,
        "entry": entry,
        "stop": stop,
        "shares": shares,
        "bars_held": bars_held,
        "ticker": ticker,
        "regime": regime,
    }


def test_basic_win_rate_and_expectancy():
    # 2 wins (+200, +100), 2 losses (-100, -100): win rate 50%, expectancy +25.
    trades = [_t("WIN", 200), _t("WIN", 100), _t("LOSS", -100), _t("LOSS", -100)]
    m = compute_metrics(trades, starting_capital=10_000.0)
    assert m["n_closed"] == 4
    assert m["win_rate"] == 0.5
    assert m["avg_win"] == 150.0
    assert m["avg_loss"] == -100.0
    assert m["expectancy"] == 25.0  # 0.5*150 + 0.5*-100
    assert m["total_pnl"] == 100.0
    assert m["profit_factor"] == 1.5  # 300 / 200


def test_open_trades_excluded_from_stats():
    trades = [_t("WIN", 100), _t("OPEN", 0)]
    m = compute_metrics(trades, starting_capital=10_000.0)
    assert m["n_closed"] == 1 and m["n_open"] == 1


def test_max_drawdown_tracks_peak_to_trough():
    # Equity path from 1000: +100 ->1100(peak), -300 ->800, +50 ->850.
    # Max drawdown = 1100 - 800 = 300 (27.3% of peak).
    trades = [_t("WIN", 100), _t("LOSS", -300), _t("WIN", 50)]
    m = compute_metrics(trades, starting_capital=1_000.0)
    assert m["max_drawdown"] == 300.0
    assert round(m["max_drawdown_pct"], 4) == round(300 / 1100, 4)


def test_realized_r_multiple():
    # risk/share = |100-98| = 2; shares=10 -> risk = 20.
    # WIN +40 -> +2R (clean target); LOSS -20 -> -1R (clean stop).
    trades = [_t("WIN", 40), _t("LOSS", -20)]
    m = compute_metrics(trades, starting_capital=10_000.0)
    assert m["avg_win_r"] == 2.0
    assert m["avg_loss_r"] == -1.0
    assert m["avg_r_multiple"] == 0.5  # mean(+2, -1)


def test_by_ticker_breakdown():
    trades = [_t("WIN", 100, ticker="AAA"), _t("LOSS", -50, ticker="AAA"),
              _t("WIN", 80, ticker="BBB")]
    m = compute_metrics(trades, starting_capital=10_000.0)
    assert m["by_ticker"]["AAA"]["n"] == 2
    assert m["by_ticker"]["AAA"]["win_rate"] == 0.5
    assert m["by_ticker"]["AAA"]["pnl"] == 50.0
    assert m["by_ticker"]["BBB"]["win_rate"] == 1.0


def test_by_regime_breakdown():
    trades = [_t("WIN", 100, regime="BULL"), _t("LOSS", -50, regime="BULL"),
              _t("WIN", 80, regime="CHOPPY"), _t("WIN", 60, regime=None)]
    m = compute_metrics(trades, starting_capital=10_000.0)
    assert m["by_regime"]["BULL"]["n"] == 2
    assert m["by_regime"]["BULL"]["win_rate"] == 0.5
    assert m["by_regime"]["BULL"]["pnl"] == 50.0
    assert m["by_regime"]["CHOPPY"]["win_rate"] == 1.0
    assert m["by_regime"]["UNKNOWN"]["n"] == 1  # untagged trade bucketed as UNKNOWN


def test_empty_trades():
    m = compute_metrics([], starting_capital=10_000.0)
    assert m["n_closed"] == 0
    assert m["win_rate"] == 0.0


def _seed_live_and_backtest_trade(db):
    init_db(db)
    live = {"ticker": "AAA", "direction": "LONG", "entry": 100, "stop": 98,
            "target": 104, "shares": 10, "entry_bar": 1}
    backtest = {"ticker": "BBB", "direction": "SHORT", "entry": 50, "stop": 51,
                "target": 48, "shares": 20, "entry_bar": 1}
    live_id = log_trade_open(live, db_path=db, source="live")
    backtest_id = log_trade_open(backtest, db_path=db, source="backtest")
    close_trade(live_id, {**live, "exit_price": 104, "outcome": "WIN", "pnl": 40.0,
                          "exit_bar": 5, "bars_held": 4}, db_path=db)
    close_trade(backtest_id, {**backtest, "exit_price": 47, "outcome": "WIN", "pnl": 60.0,
                              "exit_bar": 5, "bars_held": 4}, db_path=db)


def test_load_closed_trades_filters_by_source(tmp_path):
    db = str(tmp_path / "d.db")
    _seed_live_and_backtest_trade(db)

    live = load_closed_trades(db, source="live")
    backtest = load_closed_trades(db, source="backtest")
    unfiltered = load_closed_trades(db)

    assert [t["ticker"] for t in live] == ["AAA"]
    assert [t["ticker"] for t in backtest] == ["BBB"]
    assert len(unfiltered) == 2
