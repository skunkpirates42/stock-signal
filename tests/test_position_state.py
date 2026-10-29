"""Offline read-model fixtures; dashboard GETs never invoke execution."""
import json
from datetime import datetime, timedelta, timezone
import pytest
from db.logger import _connect, _insert, init_db, log_trade_open, now
from dashboard.position_state import position_state
from dashboard.app import create_app


@pytest.fixture
def journal(tmp_path):
    path = str(tmp_path / 'state.db')
    init_db(path)
    stamp = now()
    trade = dict(ticker='SPY', direction='LONG', entry=100, stop=95, target=110,
                 shares=10, remaining_shares=10, backend='alpaca', account='a', entry_order_id='parent')
    tid = log_trade_open(trade, path)
    with _connect(path) as conn:
        for oid, purpose, state, qty, payload in [
            ('parent', 'entry', 'filled', 10, {'execution_policy': 'bracket_v1'}),
            ('stop', 'exit', 'new', 0, {'parent_id': 'parent', 'exit_reason': 'stop', 'broker_qty': 10}),
            ('target', 'exit', 'accepted', 0, {'parent_id': 'parent', 'exit_reason': 'target', 'broker_qty': 10}),
        ]:
            _insert(conn, 'orders', dict(id=oid, source='live', backend='alpaca', account='a', ticker='SPY',
                    purpose=purpose, state=state, requested_qty=10, filled_qty=qty, fill_price=100 if qty else None,
                    trade_id=tid, payload_json=json.dumps(payload), updated_at=stamp))
        conn.execute('INSERT INTO broker_observations VALUES (?,?,?,?,?,?)', ('a', stamp, stamp, stamp, 'ok', '{"SPY":10}'))
    return path


def test_identity_provenance_and_read_only_endpoint(journal, tmp_path, monkeypatch):
    from trades.alpaca_broker import AlpacaBroker
    monkeypatch.setattr(AlpacaBroker, '__init__', lambda *a, **kw: pytest.fail('Dashboard instantiated execution'))
    for backend, account, source in [('local', 'a', 'live'), ('alpaca', 'b', 'live'), ('local', 'a', 'backtest')]:
        log_trade_open(dict(ticker='SPY', direction='LONG', entry=1, shares=1, backend=backend, account=account), journal, source)
    with _connect(journal) as conn:
        _insert(conn, 'trades', dict(ticker='SPY', shares=1, outcome='OPEN'))
        before = list(conn.iterdump())
    app = create_app(journal, demo_job_db_path=str(tmp_path/'jobs.db'))
    result = app.test_client().get('/api/position-state')
    assert result.status_code == 200 and result.headers['Cache-Control'] == 'no-store'
    data = result.json
    assert [p['provenance'] for p in data['positions']] == ['Alpaca paper', 'Local simulation', 'Alpaca paper', 'Replay', 'Unknown provenance']
    assert data['positions'][0]['execution']['protection'] == 'confirmed'
    assert data['positions'][2]['execution']['entry'] is None
    assert data['positions'][2]['execution']['protection'] == 'unconfirmed'
    with _connect(journal) as conn:
        assert list(conn.iterdump()) == before


@pytest.mark.parametrize('state', ['held', 'rejected', 'canceled', 'unresolved', 'pending_new'])
def test_nonactive_child_never_protected(journal, state):
    with _connect(journal) as conn:
        conn.execute('UPDATE orders SET state=? WHERE id=?', (state, 'stop'))
    execution = position_state(journal)['positions'][0]['execution']
    assert execution['protection'] == 'unconfirmed'
    assert execution['legs']['stop']['state'] == state


@pytest.mark.parametrize('mutation', [
    "DELETE FROM orders WHERE id='stop'",
    "UPDATE orders SET payload_json='{}' WHERE id='stop'",
    "UPDATE orders SET account='b' WHERE id='stop'",
    "UPDATE orders SET trade_id=999 WHERE id='stop'",
    "UPDATE orders SET state='partially_filled',filled_qty=5 WHERE id='parent'",
    "UPDATE orders SET payload_json='{}' WHERE id='parent'",
    "UPDATE orders SET payload_json='{\"parent_id\":\"parent\",\"exit_reason\":\"stop\",\"broker_qty\":5}' WHERE id='stop'",
    "UPDATE orders SET updated_at=NULL WHERE id='stop'",
    "DELETE FROM broker_observations",
    "UPDATE broker_observations SET status='unconfirmed'",
])
def test_incomplete_evidence(journal, mutation):
    with _connect(journal) as conn:
        conn.execute(mutation)
    assert position_state(journal)['positions'][0]['execution']['protection'] == 'unconfirmed'


def test_stale_mismatch_empty_and_pending(journal):
    later = datetime.now(timezone.utc) + timedelta(seconds=31)
    data = position_state(journal, later)
    assert data['accounts'][0]['status'] == 'stale'
    assert data['positions'][0]['execution']['protection'] == 'unconfirmed'
    with _connect(journal) as conn:
        conn.execute("UPDATE broker_observations SET positions_json='{}'")
    assert position_state(journal)['accounts'][0]['status'] == 'mismatch'
    with _connect(journal) as conn:
        conn.execute("DELETE FROM trades")
        conn.execute("UPDATE orders SET trade_id=NULL,state='unresolved',filled_qty=0 WHERE id='parent'")
    data = position_state(journal)
    assert data['pending_entries'][0]['state'] == 'unresolved'
    # Empty holdings does not mean there are no pending orders.
    assert data['accounts'][0]['status'] == 'confirmed empty'


def test_closed_exit_no_protection_warning(journal):
    with _connect(journal) as conn:
        conn.execute("UPDATE trades SET outcome='LOSS',remaining_shares=0,exit_price=94")
        conn.execute("UPDATE orders SET state='filled',filled_qty=10,fill_price=94 WHERE id='stop'")
        conn.execute("UPDATE orders SET state='canceled' WHERE id='target'")
        conn.execute("UPDATE broker_observations SET positions_json='{}'")
    data = position_state(journal)
    assert data['positions'] == []
    assert data['exit_fills'][0]['fill_price'] == 94
    assert len(data['closed_trades']) == 1


def test_pending_session_close(journal):
    with _connect(journal) as conn:
        conn.execute("UPDATE trades SET state_json='{\"reason\":\"session_close\"}'")
    execution = position_state(journal)['positions'][0]['execution']
    assert execution['pending_exit'] == 'session_close'
    assert execution['protection'] == 'unconfirmed'


def test_worker_observation_success_and_failure(tmp_path):
    from tests.test_alpaca_brackets import setup
    client, broker = setup(tmp_path)
    assert broker.reconcile()
    first = position_state(broker.db_path)['accounts'][0]
    assert first['reconciled_at'] and first['observed_at']
    client.fail = 'positions'
    assert not broker.reconcile()
    second = position_state(broker.db_path)['accounts'][0]
    assert second['observation_status'] == 'unconfirmed'
    assert second['observed_at'] == first['observed_at']
    assert second['reconciled_at'] == first['reconciled_at']


def test_zero_fill_entry_has_scoped_children_and_levels(journal):
    with _connect(journal) as conn:
        conn.execute('DELETE FROM trades')
        conn.execute('UPDATE orders SET trade_id=NULL')
        conn.execute("UPDATE orders SET state='held' WHERE purpose='exit'")
        conn.execute("UPDATE orders SET state='new',filled_qty=0,payload_json='{\"execution_policy\":\"bracket_v1\",\"stop\":95,\"target\":110}' WHERE id='parent'")
    entry = position_state(journal)['pending_entries'][0]
    assert entry['stop'] == 95 and entry['target'] == 110
    assert entry['execution']['legs']['stop']['state'] == 'held'
    assert entry['execution']['protection'] == 'unconfirmed'


def test_observation_write_failure_preserves_execution_result(tmp_path, monkeypatch):
    from tests.test_alpaca_brackets import setup
    client, broker = setup(tmp_path)
    with _connect(broker.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_observation BEFORE INSERT ON broker_observations BEGIN SELECT RAISE(FAIL, 'telemetry failure'); END")
    assert broker.reconcile() is True
    assert broker.safe_to_flatten is True
    parent = client.submitted[0]
    client.fill(parent + '-stop', 100, 97)
    client.orders[parent + '-limit'].status = 'canceled'
    assert broker.reconcile() is True
    assert not broker.has_open('NVDA')
