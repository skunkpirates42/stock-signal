"""Opt-in, causal research gates; definitions are versioned independently of votes."""
import math
import statistics
import pandas as pd
from data.sessions import calendar, session_bounds, utc

POLICY = {
    'version': 'quality_v2', 'strength_lookback_bars': 12,
    'strength_threshold': 0, 'benchmark': 'SPY',
    'rvol_prior_sessions': 20, 'rvol_min_observations': 10,
    'rvol_threshold': 1.5, 'bar_minutes': 5,
}


class ResearchGate:
    def __init__(self, bars, mode):
        if mode not in ('baseline', 'strength', 'rvol', 'both'):
            raise ValueError('Unknown research gate')
        self.mode = mode
        self.bars = {}
        for symbol, df in bars.items():
            frame = df.copy()
            frame['timestamp'] = pd.to_datetime(frame.timestamp, utc=True)
            if frame.timestamp.duplicated().any():
                raise ValueError('Gate inputs must have unique timestamps')
            self.bars[symbol] = frame.set_index('timestamp').sort_index()
        self._session_cache = {}

    def _prior_sessions(self, ts):
        day = str(ts.tz_convert('America/New_York').date())
        if day not in self._session_cache:
            cal = calendar(int(day[:4]))
            days = [str(d.date()) for d in cal.sessions if str(d.date()) < day][-20:]
            self._session_cache[day] = [session_bounds(d + 'T17:00Z') for d in days]
        return self._session_cache[day]

    def _strength(self, symbol, ts, direction, pair):
        detail = {'value': None, 'threshold': 0, 'benchmark': 'SPY',
                  'accepted': False, 'reason': 'missing_endpoints'}
        if symbol == 'SPY':
            return {**detail, 'accepted': True, 'reason': 'not_applicable'}
        start = ts - pd.Timedelta(minutes=60)
        if start < pair[0]:
            return {**detail, 'reason': 'insufficient_current_session'}
        stock, benchmark = self.bars.get(symbol), self.bars.get('SPY')
        if stock is None or benchmark is None:
            return detail
        if not all(t in frame.index for frame in (stock, benchmark) for t in (start, ts)):
            return detail
        prices = [float(frame.at[t, 'close']) for frame in (stock, benchmark) for t in (start, ts)]
        if not all(math.isfinite(p) and p > 0 for p in prices):
            return {**detail, 'reason': 'invalid_prices'}
        value = math.log(prices[1]) - math.log(prices[0]) - math.log(prices[3]) + math.log(prices[2])
        accepted = value > 0 if direction == 'LONG' else value < 0
        return {**detail, 'value': value, 'accepted': accepted,
                'reason': 'passed' if accepted else 'direction_mismatch_or_equal'}

    def _rvol(self, symbol, ts, pair):
        detail = {'value': None, 'threshold': 1.5, 'accepted': False,
                  'observations': 0, 'reason': 'missing_current_bar'}
        stock = self.bars.get(symbol)
        if stock is None or ts not in stock.index:
            return detail
        current = float(stock.at[ts, 'volume'])
        if not math.isfinite(current) or current < 0:
            return {**detail, 'reason': 'invalid_current_volume'}
        offset = ts - pair[0]
        volumes = []
        for opening, closing in self._prior_sessions(ts):
            bucket = opening + offset
            if bucket + pd.Timedelta(minutes=5) > closing or bucket not in stock.index:
                continue
            volume = float(stock.at[bucket, 'volume'])
            if math.isfinite(volume) and volume >= 0:
                volumes.append(volume)
        detail['observations'] = len(volumes)
        if len(volumes) < 10:
            return {**detail, 'reason': 'insufficient_prior_sessions'}
        median = statistics.median(volumes)
        if median <= 0:
            return {**detail, 'reason': 'zero_reference_volume'}
        value = current / median
        if not math.isfinite(value):
            return {**detail, 'reason': 'invalid_ratio'}
        accepted = value >= 1.5
        return {**detail, 'value': value, 'reference_median': median,
                'accepted': accepted, 'reason': 'passed' if accepted else 'below_threshold'}

    def __call__(self, symbol, windows, decision_at, direction):
        detail = {'mode': self.mode, 'policy': POLICY, 'strength': None,
                  'rvol': None, 'accepted': True, 'checks': {}}
        if self.mode == 'baseline':
            return True, detail
        ts = utc(decision_at) - pd.Timedelta(minutes=5)
        pair = session_bounds(ts)
        if (direction not in ('LONG', 'SHORT') or not pair or ts < pair[0]
                or ts + pd.Timedelta(minutes=5) > pair[1]
                or (ts - pair[0]) % pd.Timedelta(minutes=5) != pd.Timedelta(0)):
            return False, {**detail, 'accepted': False, 'reason': 'invalid_decision_context'}
        if self.mode in ('strength', 'both'):
            detail['checks']['strength'] = self._strength(symbol, ts, direction, pair)
        if self.mode in ('rvol', 'both'):
            detail['checks']['rvol'] = self._rvol(symbol, ts, pair)
        for name, check in detail['checks'].items():
            detail[name] = check['value']
        detail['accepted'] = all(c['accepted'] for c in detail['checks'].values())
        detail['reason'] = 'passed' if detail['accepted'] else 'quality_gate'
        return detail['accepted'], detail
