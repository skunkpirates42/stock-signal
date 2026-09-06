"""Versioned SQLite journal. Audit timestamps never stand in for execution time."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
import config

SIGNALS = {
    'ticker': 'TEXT', 'bar_timestamp': 'TEXT', 'direction': 'TEXT', 'confidence': 'REAL',
    'entry': 'REAL', 'stop': 'REAL', 'target': 'REAL', 'rr': 'REAL',
    'indicators_json': 'TEXT', 'reasoning': 'TEXT', 'regime': 'TEXT', 'source': 'TEXT',
    'synthesis_source': 'TEXT', 'created_at': 'TEXT', 'run_id': 'TEXT',
    'decision_at': 'TEXT', 'skip_reason': 'TEXT', 'gate_json': 'TEXT',
    'backend': 'TEXT', 'account': 'TEXT',
}
TRADES = {
    'signal_id': 'INTEGER', 'ticker': 'TEXT', 'direction': 'TEXT', 'entry': 'REAL',
    'stop': 'REAL', 'target': 'REAL', 'shares': 'INTEGER', 'exit_price': 'REAL',
    'outcome': 'TEXT', 'pnl': 'REAL', 'entry_bar': 'INTEGER', 'exit_bar': 'INTEGER',
    'bars_held': 'INTEGER', 'created_at': 'TEXT', 'closed_at': 'TEXT', 'source': 'TEXT',
    'backend': 'TEXT', 'account': 'TEXT', 'run_id': 'TEXT', 'entry_at': 'TEXT',
    'exit_at': 'TEXT', 'elapsed_seconds': 'REAL', 'gross_pnl': 'REAL', 'costs': 'REAL',
    'exit_reason': 'TEXT', 'remaining_shares': 'INTEGER', 'observed_bars': 'INTEGER DEFAULT 0',
    'entry_cost': 'REAL DEFAULT 0', 'entry_order_id': 'TEXT', 'state_json': 'TEXT',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path=None):
    conn = sqlite3.connect(db_path or config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    with _connect(db_path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY, applied_at TEXT)')
        for table, columns in [('signals', SIGNALS), ('trades', TRADES)]:
            conn.execute(f'CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY AUTOINCREMENT)')
            existing = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
            for name, kind in columns.items():
                if name not in existing:
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, source TEXT, backend TEXT, account TEXT,
                manifest_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, broker_id TEXT, source TEXT, backend TEXT, account TEXT,
                ticker TEXT, purpose TEXT, state TEXT, requested_qty INTEGER,
                filled_qty INTEGER DEFAULT 0, fill_price REAL, applied_qty INTEGER DEFAULT 0,
                signal_id INTEGER, trade_id INTEGER, payload_json TEXT, last_error TEXT,
                created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS local_pending (
                scope TEXT, ticker TEXT, payload_json TEXT, PRIMARY KEY(scope,ticker));
            CREATE TABLE IF NOT EXISTS runtime_status (
                scope TEXT PRIMARY KEY, updated_at TEXT, data_at TEXT, status TEXT, detail TEXT);
            CREATE INDEX IF NOT EXISTS trades_scope ON trades(source, backend, account, outcome);
            CREATE UNIQUE INDEX IF NOT EXISTS trade_entry_order ON trades(entry_order_id)
                WHERE entry_order_id IS NOT NULL;
        ''')
        conn.execute('INSERT OR IGNORE INTO schema_versions VALUES (1, ?)', (now(),))


def _insert(conn, table, values):
    keys = list(values)
    return conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                        [values[k] for k in keys]).lastrowid


def _update(conn, table, row_id, values):
    conn.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)} WHERE id=?",
                 list(values.values()) + [row_id])


def start_run(manifest, db_path=None):
    run_id = uuid.uuid4().hex
    with _connect(db_path) as conn:
        conn.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',
                     (run_id, manifest['source'], manifest['backend'], manifest.get('account'),
                      json.dumps(manifest, sort_keys=True), now()))
    return run_id


def log_signal(signal, bar_timestamp=None, db_path=None, source='live'):
    values = {k: signal.get(k) for k in SIGNALS if k in signal}
    values.update(source=source, bar_timestamp=str(bar_timestamp) if bar_timestamp is not None else None,
                  created_at=now())
    with _connect(db_path) as conn:
        return _insert(conn, 'signals', values)


def trade_values(position, source='live'):
    values = {k: position[k] for k in TRADES if k in position}
    values.update(source=source, outcome='OPEN', created_at=now())
    # New explicit writes are scoped; migration leaves historical unknowns untouched.
    values.setdefault('backend', 'local')
    values.setdefault('account', config.ACCOUNT_NAMESPACE)
    values.setdefault('remaining_shares', position['shares'])
    values.setdefault('observed_bars', 0)
    return values


def log_trade_open(position, db_path=None, source='live'):
    with _connect(db_path) as conn:
        return _insert(conn, 'trades', trade_values(position, source))


def close_values(trade):
    keys = ('exit_price', 'outcome', 'pnl', 'exit_bar', 'bars_held', 'exit_at',
            'elapsed_seconds', 'gross_pnl', 'costs', 'exit_reason', 'remaining_shares')
    values = {k: trade[k] for k in keys if k in trade}
    values.update(closed_at=now(), remaining_shares=0)
    return values


def close_trade(trade_id, trade, db_path=None):
    with _connect(db_path) as conn:
        _update(conn, 'trades', trade_id, close_values(trade))


def scope_sql(source=None, backend=None, account=None, prefix=''):
    clauses, params = [], []
    for key, value in [('source', source), ('backend', backend), ('account', account)]:
        if value == 'unknown':
            clauses.append(f'{prefix}{key} IS NULL')
        elif value is not None and value != 'all':
            clauses.append(f'{prefix}{key}=?')
            params.append(value)
    return clauses, params


def load_open_positions(db_path=None, source=None, backend=None, account=None):
    clauses, params = scope_sql(source, backend, account)
    clauses.insert(0, "outcome='OPEN'")
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM trades WHERE ' + ' AND '.join(clauses), params)]


def realized_pnl(db_path=None, source=None, backend=None, account=None):
    clauses, params = scope_sql(source, backend, account)
    # Partial confirmed exits also contribute to realized capital.
    with _connect(db_path) as conn:
        return float(conn.execute('SELECT COALESCE(SUM(pnl),0) FROM trades' +
                                  (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params).fetchone()[0])


def save_position(position, db_path=None):
    if not position.get('db_id'):
        return
    with _connect(db_path) as conn:
        _update(conn, 'trades', position['db_id'], {
            'observed_bars': position.get('observed_bars', 0),
            'state_json': json.dumps(position.get('pending_exit')),
        })


def set_status(scope, status, detail='', data_at=None, db_path=None):
    with _connect(db_path) as conn:
        conn.execute('INSERT INTO runtime_status VALUES (?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET '
                     'updated_at=excluded.updated_at, data_at=COALESCE(excluded.data_at,runtime_status.data_at), '
                     'status=excluded.status, detail=excluded.detail',
                     (scope, now(), str(data_at) if data_at is not None else None, status, detail))
