"""Opt-in research gates. New definitions; not a recreation of historical claims."""
import math
import pandas as pd
from data.sessions import utc


class ResearchGate:
    def __init__(self, bars, mode):
        if mode not in ('baseline','strength','rvol','both'):
            raise ValueError('Unknown research gate')
        self.mode = mode
        self.bars = {s: df.assign(timestamp=pd.to_datetime(df.timestamp, utc=True)).sort_values('timestamp')
                     for s,df in bars.items()}

    def __call__(self, symbol, windows, decision_at, direction):
        if self.mode == 'baseline':
            return True, {'mode':'baseline'}
        # Current completed bar starts five minutes before the decision time.
        ts = utc(decision_at) - pd.Timedelta(minutes=5)
        detail = {'mode':self.mode, 'strength':None, 'rvol':None, 'accepted':True}
        stock = self.bars[symbol]
        stock = stock[stock.timestamp <= ts]
        if stock.empty:
            return False, {**detail, 'accepted':False, 'reason':'missing_stock'}
        if self.mode in ('strength','both') and symbol != 'SPY':
            benchmark = self.bars.get('SPY')
            start = ts - pd.Timedelta(minutes=60)
            value = None
            if benchmark is not None and start.tz_convert('America/New_York').date() == ts.tz_convert('America/New_York').date():
                a = stock.set_index('timestamp').close
                b = benchmark.set_index('timestamp').close
                if all(t in a.index and t in b.index for t in (start,ts)):
                    value = math.log(a.loc[ts]/a.loc[start]) - math.log(b.loc[ts]/b.loc[start])
            detail['strength'] = value
            detail['accepted'] = value is not None and (value > 0 if direction=='LONG' else value < 0)
        if self.mode in ('rvol','both'):
            et = stock.timestamp.dt.tz_convert('America/New_York')
            prior = stock[(et.dt.date < ts.tz_convert('America/New_York').date()) &
                          (et.dt.hour == ts.tz_convert('America/New_York').hour) &
                          (et.dt.minute == ts.minute)].tail(20)
            value = None
            if len(prior) >= 10 and prior.volume.median() > 0 and stock.timestamp.iloc[-1] == ts:
                value = float(stock.volume.iloc[-1] / prior.volume.median())
            detail['rvol'] = value
            detail['accepted'] = detail['accepted'] and value is not None and value >= 1.5
        return bool(detail['accepted']), detail
