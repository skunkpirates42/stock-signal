"""Local fills at an explicit executable event, with adverse costs and exposure limits."""
import math
from dataclasses import dataclass
import config


@dataclass(frozen=True)
class FillPolicy:
    spread_bps: float = 0
    slippage_bps: float = 0
    fee_per_share: float = 0

    @classmethod
    def configured(cls):
        return cls(config.SPREAD_BPS, config.SLIPPAGE_BPS, config.FEE_PER_SHARE)

    def cost(self, reference, shares):
        return shares * (reference * (self.spread_bps / 2 + self.slippage_bps) / 10000 + self.fee_per_share)


class PaperBroker:
    def __init__(self, starting_capital=None, position_pct=None, policy=None):
        self.capital = starting_capital if starting_capital is not None else config.STARTING_CAPITAL
        self.position_pct = position_pct if position_pct is not None else config.POSITION_PCT
        self.policy = policy or FillPolicy.configured()
        self.open_positions = {}
        self.closed_trades = []
        self.blocked = None
        self.account = config.ACCOUNT_NAMESPACE

    def has_open(self, ticker):
        return ticker in self.open_positions

    @property
    def available(self):
        return max(0, self.capital - sum(p['entry'] * p['shares'] + p.get('entry_cost', 0)
                                       for p in self.open_positions.values()))

    def open_position(self, signal, entry_bar, signal_id=None):
        ticker = signal['ticker']
        if signal['direction'] not in ('LONG', 'SHORT') or self.has_open(ticker):
            return None
        entry = signal['entry']
        if not math.isfinite(entry) or entry <= 0:
            return None
        budget = min(self.capital * self.position_pct, self.available)
        shares = math.floor(budget / (entry + self.policy.cost(entry, 1)))
        if shares < 1:
            return None
        pos = {k: signal[k] for k in ('ticker', 'direction', 'entry', 'stop', 'target')}
        pos.update(signal_id=signal_id, shares=shares, remaining_shares=shares,
                   entry_bar=entry_bar, status='OPEN', backend='local', account=self.account,
                   entry_cost=self.policy.cost(entry, shares), observed_bars=0,
                   entry_at=signal.get('entry_at'), run_id=signal.get('run_id'))
        self.open_positions[ticker] = pos
        return pos

    def close_position(self, ticker, exit_price, outcome, exit_bar, bars_held=None,
                       exit_reason=None, exit_at=None):
        position = self.open_positions[ticker]
        if not math.isfinite(exit_price) or exit_price <= 0:
            raise ValueError('Exit requires a valid observed price')
        signed = 1 if position['direction'] == 'LONG' else -1
        gross = signed * (exit_price - position['entry']) * position['shares']
        costs = position.get('entry_cost', 0) + self.policy.cost(exit_price, position['shares'])
        pnl = round(gross - costs, 2)
        self.capital += pnl
        self.open_positions.pop(ticker)
        if bars_held is None:
            bars_held = exit_bar - position['entry_bar']
        elapsed = None
        if exit_at and position.get('entry_at'):
            from data.sessions import utc
            elapsed = max(0, (utc(exit_at) - utc(position['entry_at'])).total_seconds())
        trade = {**position, 'exit_price': exit_price, 'exit_at': str(exit_at) if exit_at else None,
                 'outcome': 'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'BREAKEVEN',
                 'exit_reason': exit_reason or outcome.lower(), 'gross_pnl': round(gross, 2),
                 'costs': round(costs, 2), 'pnl': pnl, 'exit_bar': exit_bar, 'bars_held': bars_held,
                 'elapsed_seconds': elapsed, 'remaining_shares': 0, 'status': 'CLOSED'}
        self.closed_trades.append(trade)
        return trade
