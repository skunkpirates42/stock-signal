"""Opt-in, causal research gates; definitions are versioned independently of votes."""
import math
import statistics
import pandas as pd
from signals.indicators import compute_indicators
from signals.regime import UNKNOWN, classify_context, regime_eligibility
from data.sessions import calendar, session_bounds, utc

POLICY = {
    'version': 'quality_v2', 'strength_lookback_bars': 12,
    'strength_threshold': 0, 'benchmark': 'SPY',
    'rvol_prior_sessions': 20, 'rvol_min_observations': 10,
    'rvol_threshold': 1.5, 'bar_minutes': 5,
    'regime_gate_version': 'regime_v1', 'regime_stale_minutes': 10,
}


class ResearchGate:
    def __init__(self, bars, mode):
        if mode not in ('baseline', 'strength', 'rvol', 'both', 'regime'):
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

    @staticmethod
    def _frame_at(frame, ts):
        """Return bars available at a decision's completed-bar timestamp."""
        return frame.loc[frame.index <= ts].reset_index()

    def _regime(self, ts, context=None, decision_at=None):
        if context is not None:
            return context
        freshness_at = utc(decision_at) if decision_at is not None else ts
        spy = self.bars.get('SPY')
        qqq = self.bars.get('QQQ')
        if spy is None:
            return classify_context(None)
        spy_frame = self._frame_at(spy, ts)
        if spy_frame.empty:
            return classify_context(None)
        spy_at = spy_frame['timestamp'].iloc[-1]
        if freshness_at - spy_at > pd.Timedelta(minutes=POLICY['regime_stale_minutes']):
            return classify_context(None, stale=True)
        try:
            spy_ind = compute_indicators(spy_frame)
        except (KeyError, TypeError, ValueError):
            return classify_context(None)
        qqq_ind = None
        qqq_stale = False
        if qqq is not None:
            qqq_frame = self._frame_at(qqq, ts)
            if not qqq_frame.empty:
                qqq_at = qqq_frame['timestamp'].iloc[-1]
                qqq_stale = freshness_at - qqq_at > pd.Timedelta(minutes=POLICY['regime_stale_minutes'])
                if not qqq_stale:
                    try:
                        qqq_ind = compute_indicators(qqq_frame)
                    except (KeyError, TypeError, ValueError):
                        qqq_ind = None
        return classify_context(spy_ind, qqq_ind, qqq_stale=qqq_stale)

    def __call__(self, symbol, windows, decision_at, direction, context=None):
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
        if self.mode == 'regime':
            regime_context = self._regime(ts, context=context, decision_at=decision_at)
            eligibility = regime_eligibility(direction, regime_context)
            detail['regime'] = regime_context.get('regime', UNKNOWN)
            detail['checks']['regime'] = {
                **eligibility,
                'context': dict(regime_context),
            }
            detail['accepted'] = eligibility['accepted']
            detail['reason'] = 'regime_gate:' + eligibility['reason']
            return detail['accepted'], detail
        for name, check in detail['checks'].items():
            detail[name] = check['value']
        detail['accepted'] = all(c['accepted'] for c in detail['checks'].values())
        detail['reason'] = 'passed' if detail['accepted'] else 'quality_gate'
        return detail['accepted'], detail
