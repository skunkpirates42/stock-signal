"""Signal logging to SQLite.

PoC uses stdlib sqlite3 (no SQLAlchemy/Postgres yet). Schema mirrors the `signals` table
in CLAUDE.md. Every signal is logged regardless of direction — including WAIT — so we can
later analyze how often the engine stands aside.
"""

import sqlite3
from datetime import datetime, timezone

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    bar_timestamp   TEXT,
    direction       TEXT    NOT NULL,
    confidence      REAL,
    entry           REAL,
    stop            REAL,
    target          REAL,
    rr              REAL,
    indicators_json TEXT,
    reasoning       TEXT,
    regime          TEXT,
    source          TEXT,
    synthesis_source TEXT,
    created_at      TEXT    NOT NULL
);
"""

# Columns added after the original schema shipped; applied to pre-existing DBs on init.
_MIGRATIONS = [
    "ALTER TABLE signals ADD COLUMN regime TEXT",
    "ALTER TABLE signals ADD COLUMN source TEXT",
    "ALTER TABLE signals ADD COLUMN synthesis_source TEXT",
    "ALTER TABLE trades ADD COLUMN source TEXT",
]

_TRADES_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER REFERENCES signals(id),
    ticker      TEXT    NOT NULL,
    direction   TEXT    NOT NULL,
    entry       REAL,
    stop        REAL,
    target      REAL,
    shares      INTEGER,
    exit_price  REAL,
    outcome     TEXT,           -- OPEN | WIN | LOSS
    pnl         REAL,
    entry_bar   INTEGER,
    exit_bar    INTEGER,
    bars_held   INTEGER,
    created_at  TEXT    NOT NULL,   -- when the trade was opened
    closed_at   TEXT,               -- when the trade was closed (null while OPEN)
    source      TEXT
);
"""


def _connect(db_path: str = None) -> sqlite3.Connection:
    return sqlite3.connect(db_path or config.DB_PATH)


def init_db(db_path: str = None) -> None:
    """Create the signals and trades tables if they don't exist (and run migrations)."""
    with _connect(db_path) as conn:
        conn.execute(_SCHEMA)
        conn.execute(_TRADES_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


def log_signal(signal: dict, bar_timestamp=None, db_path: str = None,
               source: str = "live") -> int:
    """Insert one signal row. Returns the new row id."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO signals
                (ticker, bar_timestamp, direction, confidence, entry, stop, target,
                 rr, indicators_json, reasoning, regime, source, synthesis_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal["ticker"],
                str(bar_timestamp) if bar_timestamp is not None else None,
                signal["direction"],
                signal.get("confidence"),
                signal.get("entry"),
                signal.get("stop"),
                signal.get("target"),
                signal.get("rr"),
                signal.get("indicators_json"),
                signal.get("reasoning"),
                signal.get("regime"),
                source,
                signal.get("synthesis_source"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def log_trade_open(position: dict, db_path: str = None, source: str = "live") -> int:
    """Insert a newly opened trade (outcome OPEN, exit fields null). Returns row id."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
                (signal_id, ticker, direction, entry, stop, target, shares,
                 outcome, entry_bar, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
            """,
            (
                position.get("signal_id"),
                position["ticker"],
                position["direction"],
                position["entry"],
                position["stop"],
                position["target"],
                position["shares"],
                position["entry_bar"],
                source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def close_trade(trade_id: int, trade: dict, db_path: str = None) -> None:
    """Update a trade row with its closing outcome (exit price, outcome, P&L, bars held)."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE trades
               SET exit_price = ?, outcome = ?, pnl = ?, exit_bar = ?, bars_held = ?,
                   closed_at = ?
             WHERE id = ?
            """,
            (
                trade["exit_price"],
                trade["outcome"],
                trade["pnl"],
                trade["exit_bar"],
                trade["bars_held"],
                datetime.now(timezone.utc).isoformat(),
                trade_id,
            ),
        )


def load_open_positions(db_path: str = None) -> list:
    """Return all still-OPEN trades as dicts (used to rebuild live state on restart)."""
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, signal_id, ticker, direction, entry, stop, target, shares,
                   entry_bar, created_at
              FROM trades
             WHERE outcome = 'OPEN'
            """
        ).fetchall()
    return [dict(r) for r in rows]


def realized_pnl(db_path: str = None) -> float:
    """Sum of P&L over all closed (WIN/LOSS) trades. Used to rebuild account capital."""
    with _connect(db_path) as conn:
        (total,) = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE outcome IN ('WIN', 'LOSS')"
        ).fetchone()
    return float(total)
