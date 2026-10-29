"""Broker-confirmed bracket lifecycle; all requests stay inside the fake client."""
from types import SimpleNamespace as NS
import pytest
from tests.test_alpaca_broker import FakeClient, LONG
from trades.alpaca_broker import AlpacaBroker
from db.logger import _connect


class BracketClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.requests = []
        self.cancels = []
        self.cancel_mode = 'confirm'

    def submit_order(self, order_data):
        self.requests.append(order_data)
        lost = self.fail == 'after'
        if lost:
            self.fail = None
        order = super().submit_order(order_data)
        if getattr(order_data.order_class, 'value', None) == 'bracket':
            order.legs = []
            for kind in ('limit', 'stop'):
                key = order.id + '-' + kind
                leg = NS(id=key, type=kind, status='new', qty=order_data.qty, filled_qty='0',
                         filled_avg_price=None, filled_at=None, symbol=order.symbol,
                         sign=-order.sign)
                order.legs.append(leg)
                self.orders[key] = leg
        if lost:
            self.fail = 'after'
            raise TimeoutError('accepted but response lost')
        return order

    def get_order_by_id(self, key, filter=None):
        return self.orders[key]

    def cancel_order_by_id(self, key):
        self.cancels.append(key)
        if self.cancel_mode == 'timeout':
            raise TimeoutError('cancel uncertain')
        if self.cancel_mode == 'confirm':
            self.orders[key].status = 'canceled'


def setup(tmp_path, direction='LONG'):
    c = BracketClient()
    b = AlpacaBroker(client=c, db_path=str(tmp_path/'brackets.db'))
    signal = LONG if direction == 'LONG' else {**LONG, 'direction':'SHORT', 'stop':102., 'target':96.}
    b.open_position(signal, 0)
    return c, b


@pytest.mark.parametrize('direction', ['LONG', 'SHORT'])
@pytest.mark.parametrize('kind,price', [('stop',97.), ('limit',105.)])
def test_confirmed_leg_fill_between_bars_restart_once(tmp_path, direction, kind, price):
    c,b = setup(tmp_path,direction)
    req = c.requests[0]
    assert req.order_class.value == 'bracket' and req.time_in_force.value == 'gtc'
    assert req.stop_loss.limit_price is None
    assert req.stop_loss.stop_price == (98 if direction == 'LONG' else 102)
    assert req.take_profit.limit_price == (104 if direction == 'LONG' else 96)
    assert b.reconcile()  # Resting legs do not globally block new entries.
    parent = c.submitted[0]
    c.fill(parent+'-'+kind,100,price)
    c.orders[parent+('-limit' if kind == 'stop' else '-stop')].status = 'canceled'
    b = AlpacaBroker(client=c,db_path=b.db_path)
    assert b.reconcile()
    assert not b.has_open('NVDA')
    assert len(b.events) == 1 and b.events[0][0] == 'close'
    assert b.events[0][1]['exit_price'] == price
    assert b.events[0][1]['exit_reason'] == ('stop' if kind == 'stop' else 'target')
    b.reconcile()
    assert len(b.events) == 1 and len(c.submitted) == 1


def test_no_bar_triggered_duplicate_and_cancel_confirmation_before_flatten(tmp_path):
    c,b = setup(tmp_path)
    assert b.close_position('NVDA',98,'LOSS',1,exit_reason='stop') is None
    assert len(c.submitted) == 1 and not c.cancels
    c.cancel_mode = 'pending'
    b.close_position('NVDA',100,'session_close',1)
    assert len(c.submitted) == 1
    c.cancel_mode = 'confirm'
    b.close_position('NVDA',100,'session_close',1)
    assert len(c.submitted) == 1
    b = AlpacaBroker(client=c,db_path=b.db_path)
    b.close_position('NVDA',100,'session_close',1)
    assert len(c.submitted) == 2 and not b.has_open('NVDA')


def test_leg_fills_during_cancel_never_sends_market_exit(tmp_path):
    c,b = setup(tmp_path)
    c.cancel_mode = 'timeout'
    b.close_position('NVDA',100,'session_close',1)
    parent = c.submitted[0]
    c.fill(parent+'-stop',100,97)
    c.orders[parent+'-limit'].status = 'canceled'
    b.close_position('NVDA',100,'session_close',1)
    assert len(c.submitted) == 1 and not b.has_open('NVDA')


def test_partial_target_then_resized_stop_cumulative_accounting(tmp_path):
    c,b = setup(tmp_path)
    parent = c.submitted[0]
    c.fill(parent+'-limit',40,104,'partially_filled')
    c.orders[parent+'-stop'].qty = 60
    assert b.reconcile()
    assert b.reconcile()
    assert b.open_positions['NVDA']['remaining_shares'] == 60
    c.orders[parent+'-limit'].status = 'canceled'
    c.fill(parent+'-stop',60,98)
    assert b.reconcile()
    with _connect(b.db_path) as conn:
        trade = conn.execute('SELECT * FROM trades').fetchone()
        assert trade['pnl'] == -10 and trade['remaining_shares'] == 0


def test_lost_entry_response_discovers_children_after_restart(tmp_path):
    c = BracketClient(); c.fail = 'after'
    b = AlpacaBroker(client=c,db_path=str(tmp_path/'brackets.db'))
    b.open_position(LONG,0)
    c.fail = None
    b = AlpacaBroker(client=c,db_path=b.db_path)
    assert b.reconcile()
    b.reconcile()
    assert len(b._orders()) == 3 and len(c.submitted) == 1


def test_missing_legs_and_double_fill_block_new_entries(tmp_path):
    c,b = setup(tmp_path)
    parent = c.submitted[0]
    c.fill(parent+'-limit',100,104)
    c.fill(parent+'-stop',100,98)
    assert not b.reconcile()
    assert len(c.submitted) == 1
    assert b.open_position({**LONG,'ticker':'MSFT'},1) is None


def test_rounding_and_invalid_levels_never_submit(tmp_path):
    c = BracketClient(); b = AlpacaBroker(client=c,db_path=str(tmp_path/'brackets.db'))
    b.open_position({**LONG,'stop':99.9999},0)
    assert not c.submitted
    b.open_position({**LONG,'stop':98.1234,'target':104.5678},0)
    assert c.requests[0].stop_loss.stop_price == 98.12
    assert c.requests[0].take_profit.limit_price == 104.57


def test_missing_children_blocks_until_nested_discovery(tmp_path):
    c,b = setup(tmp_path)
    parent = c.submitted[0]
    legs = c.orders[parent].legs
    with _connect(b.db_path) as conn:
        conn.execute("DELETE FROM orders WHERE purpose='exit'")
    c.orders[parent].legs = []
    assert not b.reconcile()
    assert 'protection incomplete' in b.blocked
    c.orders[parent].legs = legs
    assert b.reconcile()
    assert len(b._orders()) == 3


def test_partial_entry_remains_blocked_then_full_fill_links_children(tmp_path):
    c = BracketClient(); c.next_state='partially_filled'; c.partial_qty=25
    b = AlpacaBroker(client=c,db_path=str(tmp_path/'brackets.db'))
    b.open_position(LONG,0)
    assert not b.reconcile()
    assert b.open_positions['NVDA']['remaining_shares'] == 25
    c.fill(c.submitted[0],100,100.5)
    assert b.reconcile()
    assert b.open_positions['NVDA']['remaining_shares'] == 100
    assert all(o['trade_id'] == b.open_positions['NVDA']['db_id'] for o in b._orders())


def test_heartbeat_reconciles_exit_without_any_market_bar(tmp_path):
    from live.trader import LiveTrader
    c,b = setup(tmp_path)
    trader = LiveTrader(['NVDA'],b.db_path,broker=b)
    parent = c.submitted[0]
    c.fill(parent+'-stop',100,97)
    c.orders[parent+'-limit'].status = 'canceled'
    trader.tick('2026-10-28T18:01Z')
    assert not b.open_positions and len(c.submitted) == 1


def test_pending_flatten_survives_restart_and_policy_change(tmp_path,monkeypatch):
    import config
    from live.trader import LiveTrader
    c,b = setup(tmp_path)
    b.close_position('NVDA',100,'session_close',1)
    b = AlpacaBroker(client=c,db_path=b.db_path)
    assert b.open_positions['NVDA']['pending_exit']['reason'] == 'session_close'
    monkeypatch.setattr(config,'SESSION_POLICY','overnight')
    trader = LiveTrader(['NVDA'],b.db_path,broker=b)
    trader.tick('2026-10-29T14:01Z')
    assert len(c.submitted) == 2 and not b.open_positions


def test_flatten_does_not_race_undiscovered_children(tmp_path):
    c,b = setup(tmp_path)
    parent = c.submitted[0]
    with _connect(b.db_path) as conn:
        conn.execute("DELETE FROM orders WHERE purpose='exit'")
    c.orders[parent].legs = []
    b.close_position('NVDA',100,'session_close',1)
    assert len(c.submitted) == 1 and b.blocked


def test_canceled_partial_entry_is_not_considered_protected(tmp_path):
    c = BracketClient(); c.next_state='partially_filled'; c.partial_qty=25
    b = AlpacaBroker(client=c,db_path=str(tmp_path/'brackets.db'))
    b.open_position(LONG,0)
    c.orders[c.submitted[0]].status = 'canceled'
    assert not b.reconcile()
    assert 'protection incomplete' in b.blocked


@pytest.mark.parametrize('qty', [1,99,101,None,1.5])
def test_inconsistent_protective_quantity_blocks_entries(tmp_path,qty):
    c,b = setup(tmp_path)
    c.orders[c.submitted[0]+'-stop'].qty = qty
    assert not b.reconcile()
    assert b.open_position({**LONG,'ticker':'MSFT'},1) is None
    assert len(c.submitted) == 1


@pytest.mark.parametrize('direction', ['LONG','SHORT'])
@pytest.mark.parametrize('open_price,low,high', [(100,95,105),(95,94,96),(105,104,106)])
def test_touch_tie_and_gap_bars_never_duplicate_bracket_exit(tmp_path,direction,open_price,low,high):
    from live.trader import LiveTrader
    c,b = setup(tmp_path,direction)
    trader = LiveTrader(['NVDA'],b.db_path,broker=b)
    trader.process_batch({'NVDA':dict(timestamp='2026-10-28T18:00Z',open=open_price,
                                     low=low,high=high,close=open_price,volume=100)})
    assert len(c.submitted) == 1 and not c.cancels
    assert b.open_positions['NVDA']['remaining_shares'] == 100


@pytest.mark.parametrize('direction', ['LONG', 'SHORT'])
@pytest.mark.parametrize('cancel_mode', ['pending', 'timeout'])
@pytest.mark.parametrize('fill_qty', [0, 25, 100])
def test_unfilled_session_flatten_survives_restart_and_fill_race(
        tmp_path, monkeypatch, direction, cancel_mode, fill_qty):
    import config
    from live.trader import LiveTrader
    c = BracketClient()
    c.next_state = 'new'
    c.cancel_mode = cancel_mode
    b = AlpacaBroker(client=c, db_path=str(tmp_path/'flatten.db'))
    signal = LONG if direction == 'LONG' else {**LONG, 'direction':'SHORT', 'stop':102., 'target':96.}
    b.open_position(signal, 0)
    parent = c.submitted[0]
    assert not b.open_positions
    monkeypatch.setattr(config, 'SESSION_POLICY', 'flatten')
    trader = LiveTrader(['NVDA'], b.db_path, broker=b)
    trader.tick('2026-10-28T19:56:00Z')
    assert parent in c.cancels
    assert len(c.submitted) == 1
    # Restart after an unconfirmed cancellation, possibly with a racing fill.
    if fill_qty:
        c.fill(parent, fill_qty, 100.5, 'filled' if fill_qty == 100 else 'partially_filled')
    c.cancel_mode = 'confirm'
    c.next_state = 'filled'
    monkeypatch.setattr(config, 'SESSION_POLICY', 'overnight')
    b = AlpacaBroker(client=c, db_path=b.db_path)
    trader = LiveTrader(['NVDA'], b.db_path, broker=b)
    for _ in range(3):
        trader.tick('2026-10-29T13:31:00Z')
    assert not b.open_positions
    assert not b.has_open('NVDA')
    assert not c.get_all_positions()
    assert len(c.submitted) == (2 if fill_qty else 1)
    if fill_qty:
        assert c.requests[-1].qty == fill_qty
        with _connect(b.db_path) as conn:
            row = conn.execute('SELECT * FROM trades').fetchone()
            assert row['remaining_shares'] == 0 and row['exit_reason'] == 'session_close'


def test_session_flatten_cancels_unsent_entry_without_submitting(tmp_path, monkeypatch):
    import config
    from live.trader import LiveTrader
    c = BracketClient()
    b = AlpacaBroker(client=c, db_path=str(tmp_path/'unsent.db'))
    b._intent('NVDA', 'entry', 100, {**LONG, 'entry_bar':0, 'execution_policy':'bracket_v1'})
    monkeypatch.setattr(config, 'SESSION_POLICY', 'flatten')
    LiveTrader(['NVDA'], b.db_path, broker=b).tick('2026-10-28T19:56:00Z')
    assert not c.requests and not c.cancels
    assert b._orders()[0]['state'] == 'canceled'


def test_session_flatten_resolves_lost_entry_response_without_resubmitting(tmp_path, monkeypatch):
    import config
    from live.trader import LiveTrader
    c = BracketClient()
    c.next_state = 'new'
    c.fail = 'after'
    b = AlpacaBroker(client=c, db_path=str(tmp_path/'lost.db'))
    b.open_position(LONG, 0)
    c.fail = None
    b = AlpacaBroker(client=c, db_path=b.db_path)
    monkeypatch.setattr(config, 'SESSION_POLICY', 'flatten')
    trader = LiveTrader(['NVDA'], b.db_path, broker=b)
    trader.tick('2026-10-28T19:56:00Z')
    trader.tick('2026-10-28T19:56:01Z')
    assert len(c.submitted) == 1 and c.submitted[0] in c.cancels
    assert not b.has_open('NVDA')
