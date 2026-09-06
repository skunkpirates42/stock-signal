"""Fault injection against durable orders; no external orders or credentials."""
from types import SimpleNamespace as NS
from datetime import datetime, timezone
import pytest
from trades.alpaca_broker import AlpacaBroker
from db.logger import _connect

LONG = {'ticker':'NVDA','direction':'LONG','entry':100.,'stop':98.,'target':104.}


class FakeClient:
    def __init__(self):
        self.orders = {}
        self.positions = {}
        self.submitted = []
        self.fail = None
        self.next_state = 'filled'
        self.next_price = 100.5
        self.partial_qty = None

    def get_account(self):
        return NS(id='test-account', equity='100000')

    def submit_order(self, order_data):
        if self.fail == 'before':
            raise TimeoutError('request uncertain')
        key = order_data.client_order_id
        self.submitted.append(key)
        assert key not in self.orders
        qty = self.partial_qty if self.partial_qty is not None else (order_data.qty if self.next_state == 'filled' else 0)
        order = NS(id=key, status=self.next_state, filled_qty=str(qty),
                   filled_avg_price=str(self.next_price) if qty else None,
                   filled_at=datetime.now(timezone.utc), symbol=order_data.symbol,
                   sign=1 if order_data.side.value == 'buy' else -1)
        self.orders[key] = order
        self.positions[order.symbol] = self.positions.get(order.symbol, 0) + qty * order.sign
        if self.fail == 'after':
            raise TimeoutError('accepted but response lost')
        return order

    def get_order_by_id(self, key):
        return self.orders[key]

    get_order_by_client_id = get_order_by_id

    def get_all_positions(self):
        if self.fail == 'positions':
            raise ConnectionError('positions unavailable')
        return [NS(symbol=s, qty=str(q)) for s,q in self.positions.items() if q]

    def fill(self, key, qty, price, status='filled'):
        o = self.orders[key]
        self.positions[o.symbol] += (qty - float(o.filled_qty)) * o.sign
        o.filled_qty, o.filled_avg_price, o.status = str(qty), str(price), status


def broker(tmp_path, client=None):
    return AlpacaBroker(client=client or FakeClient(), db_path=str(tmp_path/'orders.db'))


def test_confirmed_entry_exit_and_outcome_from_fill(tmp_path):
    c=FakeClient(); b=broker(tmp_path,c)
    p=b.open_position(LONG,0,1)
    assert p['entry']==100.5 and p['shares']==100
    c.next_price=99
    t=b.close_position('NVDA',104,'WIN',3,exit_reason='target')
    assert t['outcome']=='LOSS' and t['pnl']==-150 and t['exit_reason']=='target'
    assert not b.has_open('NVDA')


@pytest.mark.parametrize('failure', ['before','after'])
def test_uncertain_close_preserves_exposure_and_reconciles_without_resubmit(tmp_path,failure):
    c=FakeClient(); b=broker(tmp_path,c); b.open_position(LONG,0)
    c.fail=failure
    assert b.close_position('NVDA',104,'WIN',2) is None
    assert b.has_open('NVDA')
    restarted=broker(tmp_path,c)
    c.fail=None
    restarted.reconcile()
    if failure=='after':
        assert not restarted.has_open('NVDA')
    else:
        assert restarted.has_open('NVDA') and restarted.blocked
    assert len(c.submitted)==(2 if failure=='after' else 1)


def test_entry_acceptance_response_lost_restart_adopts_once(tmp_path):
    c=FakeClient(); c.fail='after'; b=broker(tmp_path,c)
    assert b.open_position(LONG,0) is None
    c.fail=None
    b=broker(tmp_path,c)
    assert b.reconcile()
    b.reconcile()
    assert b.open_positions['NVDA']['shares']==100
    assert len(c.submitted)==1
    with _connect(b.db_path) as conn:
        assert conn.execute('SELECT count(*) FROM trades').fetchone()[0]==1


def test_partial_exit_cumulative_prices_apply_once(tmp_path):
    c=FakeClient(); b=broker(tmp_path,c); b.open_position(LONG,0)
    c.next_state='partially_filled'; c.partial_qty=40; c.next_price=102
    assert b.close_position('NVDA',104,'WIN',2) is None
    assert b.open_positions['NVDA']['remaining_shares']==60
    assert b.open_positions['NVDA']['pnl']==60
    key=c.submitted[-1]
    b.reconcile(); b.reconcile()
    assert b.open_positions['NVDA']['pnl']==60
    c.fill(key,100,103)
    b.reconcile(); b.reconcile()
    assert not b.has_open('NVDA')
    with _connect(b.db_path) as conn:
        t=conn.execute('SELECT * FROM trades').fetchone()
        assert t['pnl']==250 and t['outcome']=='WIN'


def test_partial_entry_and_cancellation_preserve_filled_exposure(tmp_path):
    c=FakeClient(); c.next_state='partially_filled'; c.partial_qty=25
    b=broker(tmp_path,c); b.open_position(LONG,0)
    assert b.open_positions['NVDA']['shares']==25
    assert b.open_position(LONG,1) is None
    c.orders[c.submitted[-1]].status='canceled'
    assert b.reconcile()
    assert b.open_positions['NVDA']['remaining_shares']==25


def test_rejected_exit_does_not_close_trade(tmp_path):
    c=FakeClient(); b=broker(tmp_path,c); b.open_position(LONG,0)
    c.next_state='rejected'
    assert b.close_position('NVDA',104,'WIN',2) is None
    assert b.open_positions['NVDA']['remaining_shares']==100


def test_reconciliation_failure_is_not_empty_account(tmp_path):
    c=FakeClient(); b=broker(tmp_path,c); c.fail='positions'
    assert not b.reconcile()
    assert 'unavailable' in b.blocked
    assert b.open_position(LONG,0) is None


def test_quantity_and_direction_drift_blocks_entries(tmp_path):
    c=FakeClient(); b=broker(tmp_path,c); b.open_position(LONG,0)
    c.positions['NVDA']=-100
    assert not b.reconcile()
    assert 'mismatch' in b.blocked


def test_missing_confirmed_price_remains_unresolved(tmp_path):
    c=FakeClient(); c.next_price=None; b=broker(tmp_path,c)
    assert b.open_position(LONG,0) is None
    assert b.has_open('NVDA')
    assert b.blocked


def test_persisted_intent_before_submission_recovers_once(tmp_path):
    c=FakeClient(); b=broker(tmp_path,c)
    b._intent('NVDA','entry',100,{**LONG,'entry_bar':0})
    b=broker(tmp_path,c)
    assert b.reconcile()
    b.reconcile()
    assert len(c.submitted)==1 and b.open_positions['NVDA']['shares']==100


def test_sdk_requests_are_bounded_and_never_automatically_retried(monkeypatch):
    monkeypatch.setenv('ALPACA_API_KEY','test-key')
    monkeypatch.setenv('ALPACA_SECRET_KEY','test-secret')
    from alpaca.trading.client import TradingClient
    calls=[]
    monkeypatch.setattr(TradingClient,'_one_request',lambda self,method,url,opts,retry: calls.append((opts,retry)))
    client=AlpacaBroker._build_client()
    client._one_request('GET','https://example.invalid',{},5)
    assert calls==[({'timeout':(3,10)},0)]
    assert client._retry==0


def test_worker_failure_clears_only_after_successful_recovery(tmp_path):
    from live.trader import LiveTrader
    c = FakeClient(); b = broker(tmp_path,c)
    t = LiveTrader(['NVDA'],b.db_path,broker=b)
    t.worker_error = b.blocked = 'worker failed'
    t.tick('2026-06-10T14:00Z')
    assert b.blocked == 'worker failed'
    c.fail = 'positions'
    t.recover_worker_error()
    assert t.worker_error and b.blocked
    c.fail = None
    t.recover_worker_error()
    assert t.worker_error is None and b.blocked is None
