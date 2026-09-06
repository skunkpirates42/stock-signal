"""Provenance columns: source (live|backtest) and synthesis_source (provider:model).

Covers the ALTER-based migration path against a pre-existing database, since the live
papertrader.db predates these columns.
"""

import sqlite3

from db.logger import close_trade, init_db, log_signal, log_trade_open, realized_pnl


def _signal(**over):
    base = {"ticker": "AAA", "direction": "LONG", "confidence": 0.7, "entry": 100.0,
            "stop": 98.0, "target": 104.0, "rr": 2.0, "indicators_json": "{}",
            "reasoning": "because"}
    base.update(over)
    return base


def _position(**over):
    base = {"signal_id": 1, "ticker": "AAA", "direction": "LONG", "entry": 100.0,
            "stop": 98.0, "target": 104.0, "shares": 10, "entry_bar": 1}
    base.update(over)
    return base


def _row(db, table, row_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM %s WHERE id = ?" % table, (row_id,)).fetchone()
    conn.close()
    return dict(row)


def _columns(db, table):
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
    conn.close()
    return cols


def test_migration_adds_columns_to_preexisting_db(tmp_path):
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "ticker TEXT NOT NULL, direction TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "ticker TEXT NOT NULL, direction TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()

    init_db(db)

    assert "source" in _columns(db, "signals")
    assert "synthesis_source" in _columns(db, "signals")
    assert "source" in _columns(db, "trades")


def test_init_db_is_idempotent(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    init_db(db)
    assert "source" in _columns(db, "signals")


def test_log_signal_defaults_source_to_live(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(), db_path=db)
    assert _row(db, "signals", sid)["source"] == "live"


def test_log_signal_records_explicit_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(), db_path=db, source="backtest")
    assert _row(db, "signals", sid)["source"] == "backtest"


def test_log_signal_persists_synthesis_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(synthesis_source="anthropic:claude-haiku-4-5"), db_path=db)
    assert _row(db, "signals", sid)["synthesis_source"] == "anthropic:claude-haiku-4-5"


def test_log_signal_synthesis_source_is_null_when_absent(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(), db_path=db)
    assert _row(db, "signals", sid)["synthesis_source"] is None


def test_log_trade_open_defaults_source_to_live(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    tid = log_trade_open(_position(), db_path=db)
    assert _row(db, "trades", tid)["source"] == "live"


def test_log_trade_open_records_explicit_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    tid = log_trade_open(_position(), db_path=db, source="backtest")
    assert _row(db, "trades", tid)["source"] == "backtest"


def test_realized_pnl_filters_by_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    live_id = log_trade_open(_position(), db_path=db, source="live")
    backtest_id = log_trade_open(_position(ticker="BBB"), db_path=db, source="backtest")
    close_trade(live_id, {"exit_price": 104.0, "outcome": "WIN", "pnl": 40.0,
                          "exit_bar": 5, "bars_held": 4}, db_path=db)
    close_trade(backtest_id, {"exit_price": 47.0, "outcome": "LOSS", "pnl": -300.0,
                              "exit_bar": 5, "bars_held": 4}, db_path=db)

    assert realized_pnl(db, source="live") == 40.0
    assert realized_pnl(db, source="backtest") == -300.0
    assert realized_pnl(db) == -260.0
