"""Durable, non-polling Alpaca paper orders.

A network timeout is unresolved exposure, never a synthetic fill. All broker mutations
are called by the live worker, not the websocket ingestion callback.
"""
import json
import math
import sqlite3
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import config
from db.logger import (_connect, _insert, _update, init_db, now, trade_values,
                       load_open_positions, save_position)

TERMINAL_ORDER_STATES = {'filled', 'canceled', 'rejected', 'expired'}


def _status(order):
    return str(getattr(order.status, 'value', order.status)).lower()


def _payload(order_row):
    return json.loads(order_row['payload_json'])


def _is_bracket(order_row):
    return _payload(order_row).get('execution_policy') == 'bracket_v1'


def _parent_order_id(order_row):
    return _payload(order_row).get('parent_id')


def _float_or_default(value, default=None):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def outcome(pnl):
    return 'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'BREAKEVEN'


class AlpacaBroker:
    def __init__(self, client=None, position_pct=None, fill_timeout=None, poll_interval=None,
                 db_path=None, account=None):
        self._client = client if client is not None else self._build_client()
        self.db_path = db_path or config.DB_PATH
        init_db(self.db_path)
        acct = self._client.get_account()
        # Broker-assigned account ID, never a credential.
        identity = account or getattr(acct, 'id', None)
        if not identity:
            raise ValueError('A confirmed paper account identity is required')
        self.account = str(identity)
        self.capital = _float_or_default(acct.equity)
        if self.capital is None:
            raise ValueError('Missing account equity')
        self.position_pct = position_pct if position_pct is not None else config.POSITION_PCT
        self.closed_trades = []
        self.events = []
        self.open_positions = {}
        self.blocked = None
        self.safe_to_flatten = False
        self._reload_open_positions()

    @staticmethod
    def _build_client():
        import os
        from alpaca.trading.client import TradingClient
        config.validate_live()
        class BoundedTradingClient(TradingClient):
            # alpaca-py's REST hook has no public timeout setting. Keep this override
            # isolated and covered by the installed-SDK contract test.
            def _one_request(self, method, url, opts, retry):
                return super()._one_request(method, url, {**opts, 'timeout': (3, 10)}, 0)

        client = BoundedTradingClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET_KEY'], paper=True)
        client._retry = 0  # uncertain requests are reconciled explicitly, never blindly retried
        return client

    def _reload_open_positions(self):
        self.open_positions = {}
        for row in load_open_positions(self.db_path, 'live', 'alpaca', self.account):
            if row['ticker'] in self.open_positions:
                raise RuntimeError('Duplicate broker-scoped positions require reconciliation')
            row.update(db_id=row['id'], status='OPEN',
                       pending_exit=json.loads(row.get('state_json') or 'null'))
            if not row['pending_exit'] and row.get('entry_order_id'):
                with _connect(self.db_path) as conn:
                    parent = conn.execute('SELECT payload_json FROM orders WHERE id=? AND account=?',
                                          (row['entry_order_id'], self.account)).fetchone()
                if parent:
                    row['pending_exit'] = _payload(parent).get('pending_exit')
            self.open_positions[row['ticker']] = row

    def _orders(self, ticker=None):
        with _connect(self.db_path) as conn:
            sql = "SELECT * FROM orders WHERE backend='alpaca' AND account=?"
            params = [self.account]
            if ticker:
                sql += ' AND ticker=?'
                params.append(ticker)
            return [dict(r) for r in conn.execute(sql + ' ORDER BY created_at,id', params)]

    def has_open(self, ticker):
        return ticker in self.open_positions or any(o['state'] not in TERMINAL_ORDER_STATES for o in self._orders(ticker))

    def _intent(self, ticker, purpose, qty, payload, signal_id=None, trade_id=None):
        existing = [o for o in self._orders(ticker) if o['state'] not in TERMINAL_ORDER_STATES]
        if existing:
            return existing[0]['id']
        order_id = 'ss-' + uuid.uuid4().hex
        with _connect(self.db_path) as conn:
            _insert(conn, 'orders', dict(id=order_id, source='live', backend='alpaca', account=self.account,
                ticker=ticker, purpose=purpose, state='pending_submission', requested_qty=qty,
                signal_id=signal_id, trade_id=trade_id, payload_json=json.dumps(payload),
                created_at=now(), updated_at=now()))
        return order_id

    def _submit(self, order_id):
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
        from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest
        with _connect(self.db_path) as conn:
            row = dict(conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())
            # Persist before leaving the process. A crash here requires lookup/reconciliation.
            _update(conn, 'orders', order_id, {'state': 'unresolved', 'updated_at': now()})
        payload = _payload(row)
        buy = (payload['direction'] == 'LONG') == (row['purpose'] == 'entry')
        bracket = _is_bracket(row)
        legs = dict(order_class=OrderClass.BRACKET,
                    stop_loss=StopLossRequest(stop_price=payload['stop']),
                    take_profit=TakeProfitRequest(limit_price=payload['target'])) if bracket else {}
        try:
            order = self._client.submit_order(order_data=MarketOrderRequest(
                symbol=row['ticker'], qty=row['requested_qty'],
                side=OrderSide.BUY if buy else OrderSide.SELL,
                time_in_force=TimeInForce.GTC if bracket else TimeInForce.DAY,
                client_order_id=order_id, **legs))
            self._apply_broker_order_state(order_id, order)
            if bracket:
                self._discover_legs(order_id, order)
        except Exception as exc:
            self._mark_unresolved(order_id, exc)

    def _mark_unresolved(self, order_id, exc):
        self.blocked = str(exc)
        with _connect(self.db_path) as conn:
            _update(conn, 'orders', order_id, {'state': 'unresolved', 'last_error': str(exc), 'updated_at': now()})

    def _apply_broker_order_state(self, order_id, order):
        qty = _float_or_default(getattr(order, 'filled_qty', None), 0)
        price = _float_or_default(getattr(order, 'filled_avg_price', None))
        state = _status(order)
        fill_at = str(getattr(order, 'filled_at', None) or now())
        event = None
        with _connect(self.db_path) as conn:
            row = dict(conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())
            if qty < row['applied_qty'] or qty > row['requested_qty'] or int(qty) != qty:
                raise ValueError('Inconsistent broker cumulative quantity')
            qty = int(qty)
            if qty and (price is None or price <= 0):
                raise ValueError('Filled quantity without confirmed price')
            if state == 'filled' and qty != row['requested_qty'] and not self._is_bracket_leg(row):
                raise ValueError('Filled status without complete quantity')
            payload = _payload(row)
            if self._is_bracket_leg(row):
                broker_qty = _float_or_default(getattr(order, 'qty', None))
                if broker_qty is None or broker_qty < qty or int(broker_qty) != broker_qty:
                    raise ValueError('Invalid broker protective quantity')
                payload['broker_qty'] = int(broker_qty)
            if qty > row['applied_qty']:
                if row['purpose'] == 'entry':
                    trade_id = row['trade_id']
                    if trade_id is None:
                        pos = {**payload, 'entry': price, 'shares': qty,
                               'remaining_shares': qty, 'entry_at': fill_at,
                               'backend': 'alpaca', 'account': self.account, 'entry_order_id': order_id}
                        trade_id = _insert(conn, 'trades', trade_values(pos))
                    else:
                        _update(conn, 'trades', trade_id, {'entry': price, 'shares': qty, 'remaining_shares': qty})
                    row['trade_id'] = trade_id
                    if row['applied_qty'] == 0:
                        event = ('open', trade_id)
                else:
                    trade = dict(conn.execute('SELECT * FROM trades WHERE id=?', (row['trade_id'],)).fetchone())
                    delta = qty - row['applied_qty']
                    # Cumulative notional handles partial fills at different prices.
                    notional = qty * price - row['applied_qty'] * (row['fill_price'] or 0)
                    signed = 1 if trade['direction'] == 'LONG' else -1
                    gross = (trade['gross_pnl'] or 0) + signed * (notional - delta * trade['entry'])
                    remaining = trade['remaining_shares'] - delta
                    if remaining < 0:
                        raise ValueError('Exit quantity exceeds remaining exposure')
                    values = {'remaining_shares': remaining, 'gross_pnl': round(gross, 2),
                              'pnl': round(gross, 2), 'costs': 0,
                              'exit_reason': payload.get('exit_reason'), 'exit_at': fill_at}
                    if remaining == 0:
                        total_exit = trade['entry'] + signed * gross / trade['shares']
                        values.update(outcome=outcome(round(gross, 2)), exit_price=total_exit,
                                      closed_at=now(), bars_held=trade['observed_bars'] or 0,
                                      exit_bar=payload.get('exit_bar'),
                                      elapsed_seconds=max(0, (datetime.fromisoformat(fill_at) -
                                          datetime.fromisoformat(trade['entry_at'])).total_seconds()))
                    _update(conn, 'trades', row['trade_id'], values)
                    if remaining == 0:
                        event = ('close', row['trade_id'])
            _update(conn, 'orders', order_id, {'broker_id': str(order.id), 'state': state,
                'filled_qty': qty, 'applied_qty': qty, 'fill_price': price,
                'trade_id': row['trade_id'], 'payload_json': json.dumps(payload), 'last_error': state if state in ('rejected','expired','suspended') else None, 'updated_at': now()})
        self._reload_open_positions()
        if event:
            with _connect(self.db_path) as conn:
                payload = dict(conn.execute('SELECT * FROM trades WHERE id=?', (event[1],)).fetchone())
            self.events.append((event[0], payload))

    def _discover_legs(self, order_id, order):
        """Persist broker-generated child identities before applying their fills."""
        with _connect(self.db_path) as conn:
            parent = dict(conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())
            payload = _payload(parent)
            for leg in getattr(order, 'legs', None) or []:
                kind = str(getattr(getattr(leg, 'type', None), 'value', getattr(leg, 'type', '')))
                if kind not in ('limit', 'stop'):
                    raise ValueError('Unexpected bracket leg type')
                leg_order_id = 'leg-' + str(leg.id)
                child_payload = {'direction': payload['direction'], 'parent_id': order_id,
                                 'exit_reason': 'target' if kind == 'limit' else 'stop'}
                existing = conn.execute('SELECT id FROM orders WHERE id=?', (leg_order_id,)).fetchone()
                if not existing:
                    _insert(conn, 'orders', dict(id=leg_order_id, broker_id=str(leg.id), source='live',
                        backend='alpaca', account=self.account, ticker=parent['ticker'],
                        purpose='exit', state='new', requested_qty=parent['requested_qty'],
                        trade_id=parent['trade_id'], payload_json=json.dumps(child_payload),
                        created_at=now(), updated_at=now()))
                elif parent['trade_id'] is not None:
                    _update(conn, 'orders', leg_order_id, {'trade_id': parent['trade_id']})
        # Children may be returned before any entry fill. Record fills only once
        # the parent trade exists; unresolved child fills then block reconciliation.
        for leg in getattr(order, 'legs', None) or []:
            self._apply_broker_order_state('leg-' + str(leg.id), leg)

    @staticmethod
    def _is_bracket_leg(row):
        return bool(_parent_order_id(row))

    def has_bracket(self, ticker):
        pos = self.open_positions.get(ticker)
        return bool(pos and any(o['id'] == pos.get('entry_order_id') and _is_bracket(o)
            for o in self._orders(ticker)))

    def request_session_flatten(self):
        """Persist cancellation intent even when an entry has no trade yet."""
        with _connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM orders WHERE backend='alpaca' AND account=? "
                                "AND purpose='entry'", (self.account,)).fetchall()
            for row in rows:
                payload = _payload(row)
                if (_is_bracket(row) and
                        row['state'] not in TERMINAL_ORDER_STATES and not payload.get('pending_exit')):
                    payload['pending_exit'] = {'reason': 'session_close'}
                    _update(conn, 'orders', row['id'], {'payload_json': json.dumps(payload),
                                                      'updated_at': now()})

    def _cancel_flatten_entries(self):
        orders = self._orders()
        flatten_ids = {o['id'] for o in orders if o['purpose'] == 'entry' and
                       _payload(o).get('pending_exit')}
        for row in orders:
            parent_id = _parent_order_id(row)
            if row['state'] in TERMINAL_ORDER_STATES or not (row['id'] in flatten_ids or parent_id in flatten_ids):
                continue
            if not row['broker_id']:
                self.blocked = self.blocked or 'Flatten entry identity awaiting reconciliation'
                continue
            try:
                self._client.cancel_order_by_id(row['broker_id'])
            except Exception as exc:
                self._mark_unresolved(row['id'], exc)
        # A DELETE is only an acknowledgement. Observe terminal states next tick.

    def reconcile(self):
        self.blocked = None
        self.safe_to_flatten = False
        observed = None
        observation_at = None
        orders = self._orders()
        known_leg_counts = self._count_known_legs_by_parent(orders)
        # Parent first, then children, including fills received between bars.
        for row in orders:
            self._sync_order_with_broker(row, known_leg_counts.get(row['id'], 0))
        self._cancel_flatten_entries()
        try:
            observed = self._fetch_broker_positions()
            observation_at = now()
            self._block_on_exposure_mismatch(observed)
            orders = self._orders()
            self._block_on_unsettled_orders(orders)
            self.safe_to_flatten = self.blocked is None
            self._block_on_incomplete_bracket_protection(orders)
            self.capital = self._fetch_account_equity()
        except Exception as exc:
            self.safe_to_flatten = False
            self.blocked = f'Reconciliation unavailable: {exc}'
        self._record_broker_observation(observed, observation_at)
        return self.blocked is None

    def _record_broker_observation(self, observed_positions, observed_at):
        # Observational metadata only. Never expose broker exceptions in dashboard data.
        try:
            with _connect(self.db_path) as conn:
                conn.execute('INSERT INTO broker_observations VALUES (?,?,?,?,?,?) '
                    'ON CONFLICT(account) DO UPDATE SET attempted_at=excluded.attempted_at, '
                    'observed_at=COALESCE(excluded.observed_at,broker_observations.observed_at), '
                    'reconciled_at=COALESCE(excluded.reconciled_at,broker_observations.reconciled_at), '
                    'status=excluded.status, '
                    'positions_json=COALESCE(excluded.positions_json,broker_observations.positions_json)',
                    (self.account, now(), observed_at, now() if not self.blocked else None,
                     'ok' if not self.blocked else 'unconfirmed',
                     json.dumps(observed_positions) if observed_positions is not None else None))
        except sqlite3.Error:
            # Telemetry failure must not interrupt execution or change its result.
            # Persisted evidence retains its original timestamp and expires normally.
            pass

    @staticmethod
    def _count_known_legs_by_parent(orders):
        counts = {}
        for row in orders:
            parent_id = _parent_order_id(row)
            if parent_id:
                counts[parent_id] = counts.get(parent_id, 0) + 1
        return counts

    def _sync_order_with_broker(self, row, known_leg_count):
        if not self._needs_broker_sync(row, known_leg_count):
            return
        try:
            if row['state'] == 'pending_submission':
                self._resolve_pending_submission(row)
                return
            order = self._fetch_broker_order(row)
            self._apply_broker_order_state(row['id'], order)
            if _is_bracket(row):
                self._discover_legs(row['id'], order)
        except Exception as exc:
            self._mark_unresolved(row['id'], exc)

    @staticmethod
    def _needs_broker_sync(row, known_leg_count):
        if row['state'] not in TERMINAL_ORDER_STATES:
            return True
        return _is_bracket(row) and known_leg_count != 2 and row['applied_qty'] > 0

    def _resolve_pending_submission(self, row):
        if _is_bracket(row) and _payload(row).get('pending_exit'):
            # No request was sent: cancel the durable intent locally.
            with _connect(self.db_path) as conn:
                _update(conn, 'orders', row['id'], {'state': 'canceled', 'updated_at': now()})
            return
        self._submit(row['id'])

    def _fetch_broker_order(self, row):
        from alpaca.trading.requests import GetOrderByIdRequest
        if not row['broker_id']:
            return self._client.get_order_by_client_id(row['id'])
        if _is_bracket(row):
            return self._client.get_order_by_id(row['broker_id'], filter=GetOrderByIdRequest(nested=True))
        return self._client.get_order_by_id(row['broker_id'])

    def _fetch_broker_positions(self):
        signed_qty_by_symbol = {}
        for position in self._client.get_all_positions():
            qty = _float_or_default(position.qty)
            if qty is None:
                raise ValueError('Missing broker position quantity')
            side = str(getattr(getattr(position, 'side', None), 'value', getattr(position, 'side', ''))).lower()
            if side in ('long', 'short'):
                qty = abs(qty) * (1 if side == 'long' else -1)
            signed_qty_by_symbol[position.symbol] = qty
        return signed_qty_by_symbol

    def _block_on_exposure_mismatch(self, broker_positions):
        expected = {symbol: pos['remaining_shares'] * (1 if pos['direction'] == 'LONG' else -1)
                    for symbol, pos in self.open_positions.items()}
        if broker_positions != expected:
            self.blocked = f'Broker/DB exposure mismatch: expected={expected}, actual={broker_positions}'

    def _block_on_unsettled_orders(self, orders):
        if any(o['state'] not in TERMINAL_ORDER_STATES and not (self._is_bracket_leg(o) and
                o['state'] in ('new', 'accepted', 'held', 'partially_filled')) for o in orders):
            self.blocked = self.blocked or 'Order execution pending reconciliation'

    def _block_on_incomplete_bracket_protection(self, orders):
        by_id = {o['id']: o for o in orders}
        legs_by_trade = {}
        for row in orders:
            if self._is_bracket_leg(row):
                legs_by_trade.setdefault(row['trade_id'], []).append(row)
        for pos in self.open_positions.values():
            parent = by_id.get(pos['entry_order_id'])
            if parent and _is_bracket(parent):
                legs = [o for o in legs_by_trade.get(pos['db_id'], []) if o['state'] not in TERMINAL_ORDER_STATES]
                quantities_match = all(_payload(o).get('broker_qty', -1) -
                                       o['applied_qty'] == pos['remaining_shares'] for o in legs)
                if len(legs) != 2 or parent['state'] != 'filled' or not quantities_match:
                    self.blocked = self.blocked or 'Bracket protection incomplete; reconcile explicitly'

    def _fetch_account_equity(self):
        return _float_or_default(self._client.get_account().equity, self.capital)

    def alpaca_open_symbols(self):
        return {p.symbol for p in self._client.get_all_positions()}

    def open_position(self, signal, entry_bar, signal_id=None):
        if signal['direction'] not in ('LONG', 'SHORT') or self.has_open(signal['ticker']) or self.blocked:
            return None
        shares = math.floor(self.capital * self.position_pct / signal['entry'])
        if shares < 1:
            return None
        levels = {}
        for name in ('stop', 'target'):
            value = _float_or_default(signal.get(name))
            if value is None or value <= 0:
                return None
            tick = Decimal('0.01') if value >= 1 else Decimal('0.0001')
            levels[name] = float(Decimal(str(value)).quantize(tick, rounding=ROUND_HALF_UP))
        if not (levels['stop'] < signal['entry'] < levels['target'] if signal['direction'] == 'LONG'
                else levels['target'] < signal['entry'] < levels['stop']):
            return None
        payload = {**signal, **levels, 'entry_bar': entry_bar, 'signal_id': signal_id,
                   'execution_policy': 'bracket_v1'}
        order_id = self._intent(signal['ticker'], 'entry', shares, payload, signal_id)
        self._submit(order_id)
        return self.open_positions.get(signal['ticker'])

    def close_position(self, ticker, exit_price, outcome, exit_bar, bars_held=None, exit_reason=None):
        if self.has_bracket(ticker):
            # OHLC is never an instruction to duplicate a resting protective leg.
            if (exit_reason or outcome.lower()) in ('stop', 'target'):
                return None
            pos = self.open_positions[ticker]
            pos['pending_exit'] = {'reason': exit_reason or outcome.lower(), 'exit_bar': exit_bar}
            save_position(pos, self.db_path)
            self.reconcile()
            if ticker not in self.open_positions:
                return None
            pos = self.open_positions[ticker]
            children = [o for o in self._orders(ticker) if self._is_bracket_leg(o) and
                        _parent_order_id(o) == pos['entry_order_id']]
            if len(children) != 2:
                self.blocked = 'Bracket children unknown; flatten cannot safely proceed'
                return None
            active = [o for o in self._orders(ticker) if o['state'] not in TERMINAL_ORDER_STATES and
                      (o['trade_id'] == pos['db_id'] or o['id'] == pos['entry_order_id'])]
            for row in active:
                if not self._is_bracket_leg(row) and row['purpose'] == 'exit':
                    return None
                try:
                    self._client.cancel_order_by_id(row['broker_id'])
                except Exception as exc:
                    self._mark_unresolved(row['id'], exc)
                    return None
            if active:
                # A successful DELETE acknowledges a request, not cancellation.
                # Next heartbeat rechecks fills and confirmed terminal states.
                return None
            if not self.safe_to_flatten:
                return None
        pos = self.open_positions.get(ticker)
        if pos is None:
            return None
        if any(o['state'] not in TERMINAL_ORDER_STATES for o in self._orders(ticker)):
            return None
        payload = {'direction': pos['direction'], 'exit_reason': exit_reason or outcome.lower(),
                   'exit_bar': exit_bar}
        order_id = self._intent(ticker, 'exit', pos['remaining_shares'], payload, trade_id=pos['db_id'])
        self._submit(order_id)
        with _connect(self.db_path) as conn:
            row = dict(conn.execute('SELECT * FROM trades WHERE id=?', (pos['db_id'],)).fetchone())
        if row['outcome'] == 'OPEN':
            return None
        row['status'] = 'CLOSED'
        self.closed_trades.append(row)
        return row
