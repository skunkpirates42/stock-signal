"""Durable, non-polling Alpaca paper orders.

A network timeout is unresolved exposure, never a synthetic fill. All broker mutations
are called by the live worker, not the websocket ingestion callback.
"""
import json
import math
import uuid
from datetime import datetime
import config
from db.logger import (_connect, _insert, _update, init_db, now, trade_values,
                       load_open_positions)

TERMINAL = {'filled', 'canceled', 'rejected', 'expired', 'done_for_day', 'suspended'}


def _status(order):
    return str(getattr(order.status, 'value', order.status)).lower()


def _f(value, default=None):
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
        self.capital = _f(acct.equity)
        if self.capital is None:
            raise ValueError('Missing account equity')
        self.position_pct = position_pct if position_pct is not None else config.POSITION_PCT
        self.closed_trades = []
        self.events = []
        self.open_positions = {}
        self.blocked = None
        self._restore()

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

    def _restore(self):
        self.open_positions = {}
        for row in load_open_positions(self.db_path, 'live', 'alpaca', self.account):
            if row['ticker'] in self.open_positions:
                raise RuntimeError('Duplicate broker-scoped positions require reconciliation')
            row.update(db_id=row['id'], status='OPEN')
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
        return ticker in self.open_positions or any(o['state'] not in TERMINAL for o in self._orders(ticker))

    def _intent(self, ticker, purpose, qty, payload, signal_id=None, trade_id=None):
        existing = [o for o in self._orders(ticker) if o['state'] not in TERMINAL]
        if existing:
            return existing[0]['id']
        oid = 'ss-' + uuid.uuid4().hex
        with _connect(self.db_path) as conn:
            _insert(conn, 'orders', dict(id=oid, source='live', backend='alpaca', account=self.account,
                ticker=ticker, purpose=purpose, state='pending_submission', requested_qty=qty,
                signal_id=signal_id, trade_id=trade_id, payload_json=json.dumps(payload),
                created_at=now(), updated_at=now()))
        return oid

    def _submit(self, oid):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest
        with _connect(self.db_path) as conn:
            row = dict(conn.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone())
            # Persist before leaving the process. A crash here requires lookup/reconciliation.
            _update(conn, 'orders', oid, {'state': 'unresolved', 'updated_at': now()})
        payload = json.loads(row['payload_json'])
        buy = (payload['direction'] == 'LONG') == (row['purpose'] == 'entry')
        try:
            order = self._client.submit_order(order_data=MarketOrderRequest(
                symbol=row['ticker'], qty=row['requested_qty'],
                side=OrderSide.BUY if buy else OrderSide.SELL,
                time_in_force=TimeInForce.DAY, client_order_id=oid))
            self._record(oid, order)
        except Exception as exc:
            self._error(oid, exc)

    def _error(self, oid, exc):
        self.blocked = str(exc)
        with _connect(self.db_path) as conn:
            _update(conn, 'orders', oid, {'state': 'unresolved', 'last_error': str(exc), 'updated_at': now()})

    def _record(self, oid, order):
        qty = _f(getattr(order, 'filled_qty', None), 0)
        price = _f(getattr(order, 'filled_avg_price', None))
        state = _status(order)
        fill_at = str(getattr(order, 'filled_at', None) or now())
        event = None
        with _connect(self.db_path) as conn:
            row = dict(conn.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone())
            if qty < row['applied_qty'] or qty > row['requested_qty'] or int(qty) != qty:
                raise ValueError('Inconsistent broker cumulative quantity')
            qty = int(qty)
            if qty and (price is None or price <= 0):
                raise ValueError('Filled quantity without confirmed price')
            if state == 'filled' and qty != row['requested_qty']:
                raise ValueError('Filled status without complete quantity')
            payload = json.loads(row['payload_json'])
            if qty > row['applied_qty']:
                if row['purpose'] == 'entry':
                    tid = row['trade_id']
                    if tid is None:
                        pos = {**payload, 'entry': price, 'shares': qty,
                               'remaining_shares': qty, 'entry_at': fill_at,
                               'backend': 'alpaca', 'account': self.account, 'entry_order_id': oid}
                        tid = _insert(conn, 'trades', trade_values(pos))
                    else:
                        _update(conn, 'trades', tid, {'entry': price, 'shares': qty, 'remaining_shares': qty})
                    row['trade_id'] = tid
                    if row['applied_qty'] == 0:
                        event = ('open', tid)
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
            _update(conn, 'orders', oid, {'broker_id': str(order.id), 'state': state,
                'filled_qty': qty, 'applied_qty': qty, 'fill_price': price,
                'trade_id': row['trade_id'], 'last_error': state if state in ('rejected','expired','suspended') else None, 'updated_at': now()})
        self._restore()
        if event:
            with _connect(self.db_path) as conn:
                payload = dict(conn.execute('SELECT * FROM trades WHERE id=?', (event[1],)).fetchone())
            self.events.append((event[0], payload))

    def reconcile(self):
        self.blocked = None
        for row in self._orders():
            if row['state'] in TERMINAL:
                continue
            try:
                if row['state'] == 'pending_submission':
                    self._submit(row['id'])
                    continue
                order = (self._client.get_order_by_id(row['broker_id']) if row['broker_id'] else
                         self._client.get_order_by_client_id(row['id']))
                self._record(row['id'], order)
            except Exception as exc:
                self._error(row['id'], exc)
        try:
            actual = {}
            for p in self._client.get_all_positions():
                qty = _f(p.qty)
                if qty is None:
                    raise ValueError('Missing broker position quantity')
                side = str(getattr(getattr(p, 'side', None), 'value', getattr(p, 'side', ''))).lower()
                if side in ('long', 'short'):
                    qty = abs(qty) * (1 if side == 'long' else -1)
                actual[p.symbol] = qty
            expected = {s: p['remaining_shares'] * (1 if p['direction'] == 'LONG' else -1)
                        for s, p in self.open_positions.items()}
            if actual != expected:
                self.blocked = f'Broker/DB exposure mismatch: expected={expected}, actual={actual}'
            if any(o['state'] not in TERMINAL for o in self._orders()):
                self.blocked = self.blocked or 'Order execution pending reconciliation'
            self.capital = _f(self._client.get_account().equity, self.capital)
        except Exception as exc:
            self.blocked = f'Reconciliation unavailable: {exc}'
        return self.blocked is None

    def alpaca_open_symbols(self):
        return {p.symbol for p in self._client.get_all_positions()}

    def open_position(self, signal, entry_bar, signal_id=None):
        if signal['direction'] not in ('LONG', 'SHORT') or self.has_open(signal['ticker']) or self.blocked:
            return None
        shares = math.floor(self.capital * self.position_pct / signal['entry'])
        if shares < 1:
            return None
        payload = {**signal, 'entry_bar': entry_bar, 'signal_id': signal_id}
        oid = self._intent(signal['ticker'], 'entry', shares, payload, signal_id)
        self._submit(oid)
        return self.open_positions.get(signal['ticker'])

    def close_position(self, ticker, exit_price, outcome, exit_bar, bars_held=None, exit_reason=None):
        pos = self.open_positions[ticker]
        if any(o['state'] not in TERMINAL for o in self._orders(ticker)):
            return None
        payload = {'direction': pos['direction'], 'exit_reason': exit_reason or outcome.lower(),
                   'exit_bar': exit_bar}
        oid = self._intent(ticker, 'exit', pos['remaining_shares'], payload, trade_id=pos['db_id'])
        self._submit(oid)
        with _connect(self.db_path) as conn:
            row = dict(conn.execute('SELECT * FROM trades WHERE id=?', (pos['db_id'],)).fetchone())
        if row['outcome'] == 'OPEN':
            return None
        row['status'] = 'CLOSED'
        self.closed_trades.append(row)
        return row
