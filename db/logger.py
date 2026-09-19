"""Versioned SQLite journal. Audit timestamps never stand in for execution time."""
import json
import sqlite3
import uuid
from decimal import Decimal
from hashlib import sha256
from contextlib import contextmanager
from contextvars import ContextVar
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

# Version 1 journals have no accounting ledger.  Version 2 is deliberately additive:
# legacy trade P&L and manifests remain their original evidence, while a new scoped
# posting journal supplies an auditable accounting overlay.
ACCOUNTING_VERSION = 2
ACCOUNTING_COMPONENTS = (
    'cash_delta', 'receivable_delta', 'payable_delta', 'borrow_payable_delta',
    'refund_receivable_delta', 'repayment_liability_delta',
)


def now():
    return datetime.now(timezone.utc).isoformat()


_replay_connection = ContextVar('replay_connection', default=None)


@contextmanager
def _connect(db_path=None):
    shared = _replay_connection.get()
    if shared is not None and str(db_path or config.DB_PATH) == shared[0]:
        yield shared[1]
        return
    conn = sqlite3.connect(db_path or config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


@contextmanager
def replay_connection(db_path):
    """Offline replay only: reuse one connection; caller commits completed sessions."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    token = _replay_connection.set((str(db_path), conn))
    try:
        with conn:
            yield conn
    finally:
        _replay_connection.reset(token)
        conn.close()


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
            CREATE TABLE IF NOT EXISTS accounting_postings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL, source TEXT NOT NULL, backend TEXT NOT NULL,
                account TEXT NOT NULL, accounting_version INTEGER NOT NULL,
                logical_key TEXT NOT NULL, event_kind TEXT NOT NULL, occurred_at TEXT,
                action_key TEXT, revision_key TEXT, allocation_key TEXT, payment_id TEXT,
                cash_delta TEXT NOT NULL DEFAULT '0', receivable_delta TEXT NOT NULL DEFAULT '0',
                payable_delta TEXT NOT NULL DEFAULT '0', borrow_payable_delta TEXT NOT NULL DEFAULT '0',
                refund_receivable_delta TEXT NOT NULL DEFAULT '0',
                repayment_liability_delta TEXT NOT NULL DEFAULT '0',
                unavailable_reason TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(run_id, source, backend, account, accounting_version, logical_key));
            CREATE TABLE IF NOT EXISTS accounting_posting_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL, source TEXT NOT NULL, backend TEXT NOT NULL,
                account TEXT NOT NULL, accounting_version INTEGER NOT NULL,
                logical_key TEXT NOT NULL, existing_payload_json TEXT NOT NULL,
                conflicting_payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(run_id, source, backend, account, accounting_version, logical_key,
                       conflicting_payload_json));
            CREATE TABLE IF NOT EXISTS accounting_coverage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL, source TEXT NOT NULL, backend TEXT NOT NULL,
                account TEXT NOT NULL, accounting_version INTEGER NOT NULL,
                coverage_key TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
                affected_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                UNIQUE(run_id, source, backend, account, accounting_version, coverage_key));
            CREATE INDEX IF NOT EXISTS accounting_postings_scope
                ON accounting_postings(run_id, source, backend, account, accounting_version);
            CREATE UNIQUE INDEX IF NOT EXISTS accounting_payment_identity
                ON accounting_postings(run_id, source, backend, account, accounting_version, payment_id)
                WHERE payment_id IS NOT NULL;
        ''')
        conn.execute('INSERT OR IGNORE INTO schema_versions VALUES (1, ?)', (now(),))
        conn.execute('INSERT OR IGNORE INTO schema_versions VALUES (?, ?)', (ACCOUNTING_VERSION, now()))


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


def _decimal_text(value):
    """Canonical decimal storage for accounting amounts (never SQLite floats)."""
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, (str, int)):
        amount = Decimal(value)
    elif isinstance(value, float):
        # Existing executor values are floats; stringify rather than carry the binary
        # representation into this separate, decimal accounting ledger.
        amount = Decimal(str(value))
    else:
        raise TypeError('accounting amounts must be decimal text, Decimal, int, or float')
    if not amount.is_finite():
        raise ValueError('accounting amounts must be finite')
    return format(amount, 'f')


def stable_cashflow_key(event_kind, *, action_key=None, revision_key=None,
                        allocation_key=None, payment_id=None, charge_key=None,
                        accrual_key=None):
    """Return a portable logical identity for one economic accounting posting.

    The caller supplies the immutable action/charge, accepted revision, allocation and
    payment identifiers when they exist.  Hashing a canonical object avoids accidental
    dependence on dict order while keeping a compact SQLite key.
    """
    # A settlement's immutable payment/activity ID is its identity even when a later
    # action revision changes the economic target.  That prevents a revision from
    # replaying the same cash movement.  Accrual/correction identities include the
    # accepted revision and allocation instead.
    identity = ({'payment_id': payment_id} if payment_id else {
        'event_kind': event_kind, 'action_key': action_key,
        'revision_key': revision_key, 'allocation_key': allocation_key,
        'charge_key': charge_key, 'accrual_key': accrual_key,
    })
    encoded = json.dumps(identity, sort_keys=True, separators=(',', ':'))
    return f'{event_kind}:{sha256(encoded.encode()).hexdigest()}'


def _posting_scope(posting):
    required = ('run_id', 'source', 'backend', 'account')
    missing = [key for key in required if not posting.get(key)]
    if missing:
        raise ValueError('accounting posting requires ' + ', '.join(missing))
    return tuple(str(posting[key]) for key in required)


def _canonical_posting(posting):
    """Validate and canonicalize an immutable cash-flow posting input."""
    run_id, source, backend, account = _posting_scope(posting)
    event_kind = str(posting.get('event_kind') or '')
    if not event_kind:
        raise ValueError('accounting posting requires event_kind')
    logical_key = posting.get('logical_key') or stable_cashflow_key(
        event_kind, action_key=posting.get('action_key'),
        revision_key=posting.get('revision_key'), allocation_key=posting.get('allocation_key'),
        payment_id=posting.get('payment_id'), charge_key=posting.get('charge_key'),
        # A borrow charge's interval/day distinguishes cumulative accruals.  Its
        # occurrence is deterministic for supplied fixtures and retains true replay
        # deduplication for the same interval/day.
        accrual_key=posting.get('accrual_key') or (
            posting.get('occurred_at') if str(event_kind).endswith('accrual') else None),
    )
    values = {
        'run_id': run_id, 'source': source, 'backend': backend, 'account': account,
        'accounting_version': int(posting.get('accounting_version', ACCOUNTING_VERSION)),
        'logical_key': str(logical_key), 'event_kind': event_kind,
        'occurred_at': str(posting['occurred_at']) if posting.get('occurred_at') is not None else None,
        'action_key': posting.get('action_key'), 'revision_key': posting.get('revision_key'),
        'allocation_key': posting.get('allocation_key'), 'payment_id': posting.get('payment_id'),
        'unavailable_reason': posting.get('unavailable_reason'),
    }
    for component in ACCOUNTING_COMPONENTS:
        values[component] = _decimal_text(posting.get(component, '0'))
    # Preserve an evidence reference or scenario description without allowing it to
    # influence deduplication by insertion order.
    payload = {key: posting[key] for key in sorted(posting) if key not in {'payload_json'}}
    payload.update({component: values[component] for component in ACCOUNTING_COMPONENTS})
    values['payload_json'] = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return values


def record_cashflow_posting(posting, db_path=None):
    """Append one posting once, or quarantine a conflicting duplicate payload.

    A repeated read/replay of the same logical event returns ``duplicate`` and changes
    no balances.  A different payload under that immutable key is retained in the
    conflict journal and is intentionally not applied.
    """
    values = _canonical_posting(posting)
    scope = tuple(values[key] for key in ('run_id', 'source', 'backend', 'account', 'accounting_version'))

    def payment_matches(existing):
        """Revision metadata may differ; a payment's cash/balance evidence may not."""
        prior = json.loads(existing['payload_json'])
        fields = ('payment_id', 'event_kind', 'occurred_at', 'action_key', 'allocation_key',
                  'cash_delta', 'receivable_delta', 'payable_delta', 'borrow_payable_delta',
                  'refund_receivable_delta', 'repayment_liability_delta')
        return all(str(prior.get(field)) == str(values.get(field)) for field in fields)

    with _connect(db_path) as conn:
        existing = conn.execute(
            'SELECT id,payload_json FROM accounting_postings WHERE '
            'run_id=? AND source=? AND backend=? AND account=? AND accounting_version=? AND logical_key=?',
            scope + (values['logical_key'],),
        ).fetchone()
        if existing:
            if existing['payload_json'] == values['payload_json']:
                return {'status': 'duplicate', 'id': existing['id'], 'posting': values}
            if values['payment_id'] is not None and payment_matches(existing):
                return {'status': 'duplicate', 'id': existing['id'], 'posting': values}
            conn.execute(
                'INSERT OR IGNORE INTO accounting_posting_conflicts '
                '(run_id,source,backend,account,accounting_version,logical_key,existing_payload_json,'
                'conflicting_payload_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                scope + (values['logical_key'], existing['payload_json'], values['payload_json'], now()),
            )
            return {'status': 'conflict', 'id': existing['id'], 'posting': values}
        if values['payment_id'] is not None:
            payment = conn.execute(
                'SELECT id,payload_json FROM accounting_postings WHERE run_id=? AND source=? AND backend=? '
                'AND account=? AND accounting_version=? AND payment_id=?',
                scope + (values['payment_id'],),
            ).fetchone()
            if payment:
                if payment_matches(payment):
                    return {'status': 'duplicate', 'id': payment['id'], 'posting': values}
                conn.execute(
                    'INSERT OR IGNORE INTO accounting_posting_conflicts '
                    '(run_id,source,backend,account,accounting_version,logical_key,existing_payload_json,'
                    'conflicting_payload_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                    scope + (values['logical_key'], payment['payload_json'], values['payload_json'], now()),
                )
                return {'status': 'conflict', 'id': payment['id'], 'posting': values}
        keys = tuple(values)
        cursor = conn.execute(
            f"INSERT INTO accounting_postings ({','.join(keys)},created_at) VALUES "
            f"({','.join('?' for _ in keys)},?)",
            tuple(values[key] for key in keys) + (now(),),
        )
        return {'status': 'inserted', 'id': cursor.lastrowid, 'posting': values}


def record_accounting_coverage(coverage, db_path=None):
    """Persist an explicit coverage/unavailability statement once per scoped key."""
    run_id, source, backend, account = _posting_scope(coverage)
    key = str(coverage.get('coverage_key') or coverage.get('unavailable_reason') or '')
    if not key:
        raise ValueError('accounting coverage requires coverage_key')
    status = str(coverage.get('status', 'incomplete'))
    if status not in {'verified', 'scenario', 'incomplete', 'conflict', 'not_applicable'}:
        raise ValueError('invalid accounting coverage status')
    values = (run_id, source, backend, account,
              int(coverage.get('accounting_version', ACCOUNTING_VERSION)), key, status,
              str(coverage.get('reason', coverage.get('unavailable_reason', ''))),
              int(coverage.get('affected_count', 0)), now())
    with _connect(db_path) as conn:
        conn.execute(
            'INSERT OR IGNORE INTO accounting_coverage '
            '(run_id,source,backend,account,accounting_version,coverage_key,status,reason,affected_count,created_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)', values)


def cashflow_summary(run_id, db_path=None, source='backtest', backend='local', account=None,
                     accounting_version=ACCOUNTING_VERSION):
    """Return exact ledger balances and explicit incompleteness counts for one scope."""
    account = account or config.ACCOUNT_NAMESPACE
    params = (run_id, source, backend, account, accounting_version)
    with _connect(db_path) as conn:
        rows = conn.execute(
            'SELECT * FROM accounting_postings WHERE run_id=? AND source=? AND backend=? '
            'AND account=? AND accounting_version=? ORDER BY id', params).fetchall()
        coverage = conn.execute(
            'SELECT status,affected_count FROM accounting_coverage WHERE run_id=? AND source=? '
            'AND backend=? AND account=? AND accounting_version=?', params).fetchall()
        conflicts = conn.execute(
            'SELECT count(*) FROM accounting_posting_conflicts WHERE run_id=? AND source=? '
            'AND backend=? AND account=? AND accounting_version=?', params).fetchone()[0]
    balances = {component: Decimal('0') for component in ACCOUNTING_COMPONENTS}
    unavailable = 0
    for row in rows:
        for component in ACCOUNTING_COMPONENTS:
            balances[component] += Decimal(row[component])
        unavailable += int(bool(row['unavailable_reason']))
    unavailable += sum(row['affected_count'] for row in coverage if row['status'] in {'incomplete', 'conflict'})
    return {
        'accounting_version': accounting_version,
        'postings': len(rows), 'duplicate_safe': True, 'conflicts': int(conflicts),
        'unavailable_count': int(unavailable),
        'coverage': {status: sum(row['affected_count'] for row in coverage if row['status'] == status)
                     for status in ('verified', 'scenario', 'incomplete', 'conflict', 'not_applicable')},
        **{component: format(value, 'f') for component, value in balances.items()},
    }


def load_cashflow_postings(run_id, db_path=None, source='backtest', backend='local', account=None,
                           accounting_version=ACCOUNTING_VERSION):
    """Load immutable posting evidence for artifact export and marked review."""
    account = account or config.ACCOUNT_NAMESPACE
    with _connect(db_path) as conn:
        return [dict(row) for row in conn.execute(
            'SELECT * FROM accounting_postings WHERE run_id=? AND source=? AND backend=? '
            'AND account=? AND accounting_version=? ORDER BY occurred_at,id',
            (run_id, source, backend, account, accounting_version),
        )]


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
