"""Shared chronological bar pipeline and live minute aggregation.

Local fills use the next observed completed five-minute bar's close. This deliberately
models a five-minute execution delay, never an already-observed signal close or touched
threshold. Alpaca executes asynchronously at confirmed market fills.
"""
import json
from collections import deque
from datetime import datetime, timezone
import pandas as pd
import config
from data.sessions import utc, in_regular_hours, flatten_due, session_bounds
from data.source import get_bars
from db.logger import (init_db, load_open_positions, realized_pnl, log_signal, log_trade_open,
                       close_trade, save_position, set_status, _connect)
from signals.engine import generate_signal
from signals.indicators import compute_indicators
from signals.llm_synthesis import synthesize
from signals.regime import classify
from trades.executor import PaperBroker
from trades.tracker import check_exit


def floor_5min(ts):
    return ts.replace(minute=ts.minute // 5 * 5, second=0, microsecond=0)


class LiveTrader:
    def __init__(self, symbols, db_path=None, window_size=120, source='live', broker=None,
                 run_id=None, gate=None, evaluation_start=None):
        self.symbols = sorted(symbols)
        self.db_path = db_path or config.DB_PATH
        self.window_size = window_size
        self.source = source
        self.run_id = run_id
        self.gate = gate
        self.evaluation_start = utc(evaluation_start) if evaluation_start else None
        self.windows = {s: deque(maxlen=window_size) for s in self.symbols}
        self.buckets = {s: None for s in self.symbols}
        self.bar_count = {s: 0 for s in self.symbols}
        self.last_minute = {}
        self.last_closed = {}
        self.pending = {}
        self.ready = {}
        self.processed = {}
        self.on_event = None
        init_db(self.db_path)
        self.broker = broker or self._rebuild_broker()
        self.scope = f'{source}:{"alpaca" if self.is_alpaca else "local"}:{self.broker.account}'
        if source == 'live' and not self.is_alpaca:
            with _connect(self.db_path) as conn:
                self.pending = {r['ticker']:json.loads(r['payload_json']) for r in conn.execute(
                    'SELECT * FROM local_pending WHERE scope=?', (self.scope,))}
        self.legacy_blocked = self.broker.blocked if self.broker.blocked and 'Legacy' in self.broker.blocked else None

    @property
    def is_alpaca(self):
        return hasattr(self.broker, 'reconcile')

    def _rebuild_broker(self):
        if config.BROKER == 'alpaca' and self.source == 'live':
            from trades.alpaca_broker import AlpacaBroker
            broker = AlpacaBroker(db_path=self.db_path)
            broker.reconcile()
        else:
            broker = PaperBroker(starting_capital=config.STARTING_CAPITAL + realized_pnl(
                self.db_path, self.source, 'local', config.ACCOUNT_NAMESPACE))
            for row in load_open_positions(self.db_path, self.source, 'local', config.ACCOUNT_NAMESPACE):
                if row['ticker'] in broker.open_positions:
                    raise RuntimeError('Duplicate scoped open positions require reconciliation')
                row.update(db_id=row['id'], status='OPEN', pending_exit=json.loads(row['state_json'] or 'null'))
                broker.open_positions[row['ticker']] = row
        ambiguous = [p for p in load_open_positions(self.db_path) if
                     p['source'] in (None, 'live') and (not p['backend'] or not p['account'])]
        if ambiguous:
            broker.blocked = 'Legacy open positions have unknown execution scope; reconcile explicitly'
        return broker

    def seed(self):
        cutoff = utc(datetime.now(timezone.utc)) - pd.Timedelta(seconds=config.BAR_LATENESS_SECONDS)
        for s in self.symbols:
            df = get_bars(s, self.window_size)
            records = [r for r in df.to_dict('records') if in_regular_hours(r['timestamp']) and
                       utc(r['timestamp']) + pd.Timedelta(minutes=5) <= cutoff]
            self.windows[s] = deque(records, maxlen=self.window_size)
            if records:
                self.last_closed[s] = utc(records[-1]['timestamp'])

    def _emit(self, kind, payload):
        if self.on_event:
            self.on_event(kind, payload)

    def on_minute_bar(self, symbol, ts, open_, high, low, close, volume):
        ts = utc(ts)
        if symbol not in self.buckets or not in_regular_hours(ts):
            return None
        if ts <= self.last_minute.get(symbol, pd.Timestamp.min.tz_localize('UTC')):
            return None
        self.last_minute[symbol] = ts
        start = floor_5min(ts)
        if start <= self.last_closed.get(symbol, pd.Timestamp.min.tz_localize('UTC')):
            return None
        previous = self.buckets[symbol]
        result = None
        if previous and start != previous['start']:
            result = self._finish(symbol)
            previous = None
        if previous is None:
            self.buckets[symbol] = {'start': start, 'open': open_, 'high': high, 'low': low,
                                    'close': close, 'volume': volume, 'minutes': {ts.minute}}
        else:
            previous['high'] = max(previous['high'], high)
            previous['low'] = min(previous['low'], low)
            previous['close'] = close
            previous['volume'] += volume
            previous['minutes'].add(ts.minute)
        return result

    def _finish(self, symbol):
        b = self.buckets[symbol]
        self.buckets[symbol] = None
        self.last_closed[symbol] = b['start']
        if len(b['minutes']) != 5:
            set_status(self.scope, 'incomplete', f'{symbol}: incomplete five-minute bucket', b['start'], self.db_path)
            return None
        bar = {k: b[k] for k in ('open', 'high', 'low', 'close', 'volume')}
        bar['timestamp'] = b['start']
        self.ready.setdefault(b["start"], {})[symbol] = bar
        self._drain_ready()
        return bar

    def _drain_ready(self, force=False):
        for ts in sorted(list(self.ready)):
            if force or set(self.ready[ts]) == set(self.symbols):
                self.process_batch(self.ready.pop(ts))
            else:
                break

    def tick(self, ts=None):
        ts = utc(ts or datetime.now(timezone.utc))
        for s, b in list(self.buckets.items()):
            if b and ts >= b['start'] + pd.Timedelta(minutes=5, seconds=config.BAR_LATENESS_SECONDS):
                self._finish(s)
        self._drain_ready(force=True)
        if self.is_alpaca:
            self.broker.reconcile()
            if self.legacy_blocked:
                self.broker.blocked = self.legacy_blocked
            if config.SESSION_POLICY == 'flatten' and flatten_due(ts):
                for s, pos in list(self.broker.open_positions.items()):
                    self.broker.close_position(s, pos['entry'], 'session_close', self.bar_count.get(s, 0),
                                               exit_reason='session_close')
        self._broker_events()
        set_status(self.scope, 'blocked' if self.broker.blocked else 'running',
                   self.broker.blocked or 'Worker heartbeat; data freshness is separate', db_path=self.db_path)

    def _broker_events(self):
        if self.is_alpaca:
            while self.broker.events:
                kind, payload = self.broker.events.pop(0)
                self._emit(kind, payload)

    def _regime(self, decision_at):
        values = {}
        for sym in ('SPY', 'QQQ'):
            window = [b for b in self.windows.get(sym, []) if utc(b['timestamp']) + pd.Timedelta(minutes=5) <= decision_at]
            if len(window) < config.WARMUP_BARS or decision_at - utc(window[-1]['timestamp']) > pd.Timedelta(minutes=10):
                return None
            values[sym] = compute_indicators(pd.DataFrame(window))
        return classify(values['SPY'], values['QQQ'])

    def process_batch(self, bars):
        """All bars in a batch have the same start timestamp; exits precede entries."""
        bars = {s:b for s,b in bars.items() if s not in self.processed or utc(b['timestamp']) > self.processed[s]}
        if not bars:
            return {}
        times = {utc(b['timestamp']) for b in bars.values()}
        if len(times) != 1:
            raise ValueError('Batch timestamps differ')
        ts = times.pop()
        if not in_regular_hours(ts):
            return {}
        decision_at = ts + pd.Timedelta(minutes=5)
        for s, bar in sorted(bars.items()):
            self.processed[s] = ts
            self.windows[s].append({**bar, 'timestamp': ts})
            self.bar_count[s] += 1
        if self.evaluation_start is not None and ts < self.evaluation_start:
            return {}
        executable = decision_at < session_bounds(ts)[1]
        exited = set()
        # Execute previously queued exits at the newly observed close, before allocation.
        for s, bar in sorted(bars.items()):
            pos = self.broker.open_positions.get(s)
            if not pos:
                continue
            pos['observed_bars'] = (pos.get('observed_bars') or 0) + 1
            pending_exit = pos.get('pending_exit')
            flatten = config.SESSION_POLICY == 'flatten' and flatten_due(decision_at)
            if not self.is_alpaca and executable and (pending_exit or flatten):
                reason = pending_exit['reason'] if pending_exit else 'session_close'
                trade = self.broker.close_position(s, float(bar['close']), reason, self.bar_count[s],
                    bars_held=pos['observed_bars'], exit_reason=reason, exit_at=decision_at.isoformat())
                close_trade(pos['db_id'], trade, self.db_path)
                self._emit('close', trade)
                exited.add(s)
                continue
            trigger = check_exit(pos, bar)
            if trigger:
                if self.is_alpaca:
                    trade = self.broker.close_position(s, trigger['exit_price'], trigger['outcome'], self.bar_count[s],
                                                       exit_reason=trigger['reason'])
                    self._broker_events()
                    exited.add(s)
                else:
                    pos['pending_exit'] = trigger
            save_position(pos, self.db_path)
        # Execute prior candidates only on a later observation, with deterministic sizing.
        for s, bar in sorted(bars.items()):
            pending = self.pending.pop(s, None)
            if self.source == 'live' and not self.is_alpaca:
                with _connect(self.db_path) as conn:
                    conn.execute('DELETE FROM local_pending WHERE scope=? AND ticker=?', (self.scope,s))
            if pending and executable and not self.broker.has_open(s) and s not in exited and not self.broker.blocked:
                same_session = utc(pending['decision_at']).date() == ts.date()
                if same_session and pd.Timedelta(0) < decision_at - utc(pending['decision_at']) <= pd.Timedelta(minutes=10) and not (
                        config.SESSION_POLICY == 'flatten' and decision_at >= session_bounds(ts)[1] - pd.Timedelta(minutes=5)):
                    fill = {**pending, 'entry': float(bar['close']), 'entry_at': decision_at.isoformat()}
                    pos = self.broker.open_position(fill, self.bar_count[s], pending['signal_id'])
                    if pos:
                        pos['db_id'] = log_trade_open(pos, self.db_path, self.source)
                        self._emit('open', pos)
        results = {}
        for s, bar in sorted(bars.items()):
            if len(self.windows[s]) < config.WARMUP_BARS:
                continue
            signal = generate_signal(s, compute_indicators(pd.DataFrame(list(self.windows[s]))))
            signal.update(regime=self._regime(decision_at), decision_at=decision_at.isoformat(), run_id=self.run_id,
                          backend="alpaca" if self.is_alpaca else "local", account=self.broker.account)
            reason = signal.get('skip_reason') or ('wait' if signal['direction'] == 'WAIT' else None)
            if not executable:
                reason = 'session_closed'
            if self.broker.has_open(s):
                reason = 'position_or_order_open'
            elif s in exited:
                reason = 'exited_this_bar'
            elif self.broker.blocked:
                reason = 'execution_unresolved'
            elif config.SESSION_POLICY == 'flatten' and decision_at >= session_bounds(ts)[1] - pd.Timedelta(minutes=10):
                reason = 'session_closing'
            if self.gate and not reason:
                accepted, detail = self.gate(s, self.windows, decision_at, signal['direction'])
                signal['gate_json'] = json.dumps(detail)
                if not accepted:
                    reason = 'quality_gate'
            signal['skip_reason'] = reason
            synthesize(signal, provider='template')
            sid = log_signal(signal, ts, self.db_path, self.source)
            self._emit('signal', signal)
            if not reason:
                if self.is_alpaca:
                    pos = self.broker.open_position(signal, self.bar_count[s], sid)
                    self._broker_events()
                else:
                    self.pending[s] = {**signal, 'signal_id': sid}
                    if self.source == 'live':
                        with _connect(self.db_path) as conn:
                            conn.execute('INSERT OR REPLACE INTO local_pending VALUES (?,?,?)',
                                         (self.scope,s,json.dumps(self.pending[s])))
            results[s] = signal
        set_status(self.scope, 'blocked' if self.broker.blocked else 'running', self.broker.blocked or '',
                   decision_at, self.db_path)
        return results

    def _on_bar_close(self, symbol, bar):
        return self.process_batch({symbol: bar}).get(symbol)

    @staticmethod
    def _bars_between(entry_ts, exit_ts):
        # Kept for consumers needing elapsed duration; persisted bars use observed counts.
        return max(0, round((exit_ts-entry_ts).total_seconds()/300)) if entry_ts else None
