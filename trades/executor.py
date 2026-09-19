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
        # This is a local accounting overlay, deliberately separate from ``capital``.
        # ``capital`` remains the legacy closed-trade P&L basis so old journals and
        # no-flow replays retain byte-for-byte trade economics.
        self.accounting_cash = 0.0
        self.receivables = 0.0
        self.distribution_payables = 0.0
        self.borrow_payables = 0.0
        self.refund_receivables = 0.0
        self.repayment_liabilities = 0.0
        self.accounting_unavailable = 0

    def has_open(self, ticker):
        return ticker in self.open_positions

    @property
    def available(self):
        if self.accounting_unavailable:
            return 0
        return max(0, self.sizing_capital - self.reserved)

    @property
    def reserved(self):
        """Existing gross-notional reservation; short proceeds never fund new entries."""
        return sum(p['entry'] * p['shares'] + p.get('entry_cost', 0)
                   for p in self.open_positions.values())

    @property
    def sizing_capital(self):
        """Causal local capital policy from the accounting contract.

        Settled accounting cash can fund the portfolio.  Long/refund receivables are
        excluded until cash arrives; known short-distribution, borrow and repayment
        obligations reserve capital immediately.  Missing required inputs freeze new
        allocation but never invent a cover or alter a saved exit.
        """
        return (self.capital + self.accounting_cash - self.distribution_payables
                - self.borrow_payables - self.repayment_liabilities)

    def apply_accounting_posting(self, posting):
        """Apply one already-deduplicated ledger posting to the local capital overlay."""
        if posting.get('unavailable_reason'):
            self.accounting_unavailable += 1
            self.blocked = self.blocked or 'Accounting inputs unavailable; new allocations are frozen'
            return
        fields = {
            'cash_delta': 'accounting_cash',
            'receivable_delta': 'receivables',
            'payable_delta': 'distribution_payables',
            'borrow_payable_delta': 'borrow_payables',
            'refund_receivable_delta': 'refund_receivables',
            'repayment_liability_delta': 'repayment_liabilities',
        }
        for source, target in fields.items():
            delta = float(posting.get(source, 0))
            value = getattr(self, target) + delta
            # The durable ledger represents corrections as explicit opposite deltas;
            # negative balance accounts are invalid rather than silently netted.
            if target != 'accounting_cash' and value < -1e-9:
                raise ValueError(f'accounting posting would make {target} negative')
            setattr(self, target, value if target == 'accounting_cash' else max(0.0, value))

    def accounting_state(self):
        """Expose the local overlay without relabeling it as broker cash or profitability."""
        return {
            'cash': self.accounting_cash, 'receivables': self.receivables,
            'distribution_payables': self.distribution_payables,
            'borrow_payables': self.borrow_payables,
            'refund_receivables': self.refund_receivables,
            'repayment_liabilities': self.repayment_liabilities,
            'sizing_capital': self.sizing_capital, 'available_capital': self.available,
            'capital_unavailable_count': self.accounting_unavailable,
        }

    def restore_accounting_state(self, summary):
        """Rebuild the local overlay from a scoped durable ledger summary.

        ``capital`` remains the separately restored legacy trade-capital basis.  The
        caller must supply a summary for the same source/backend/account/run scope;
        an unscoped or incomplete summary is never treated as a zero balance.
        """
        required = ('cash_delta', 'receivable_delta', 'payable_delta', 'borrow_payable_delta',
                    'refund_receivable_delta', 'repayment_liability_delta', 'unavailable_count')
        if any(key not in summary for key in required):
            raise ValueError('cannot restore accounting overlay without a complete scoped summary')
        fields = {
            'cash_delta': 'accounting_cash', 'receivable_delta': 'receivables',
            'payable_delta': 'distribution_payables', 'borrow_payable_delta': 'borrow_payables',
            'refund_receivable_delta': 'refund_receivables',
            'repayment_liability_delta': 'repayment_liabilities',
        }
        for source, target in fields.items():
            value = float(summary[source])
            if target != 'accounting_cash' and value < -1e-9:
                raise ValueError(f'invalid negative restored {target}')
            setattr(self, target, value)
        self.accounting_unavailable = int(summary['unavailable_count'])
        if self.accounting_unavailable:
            self.blocked = self.blocked or 'Accounting inputs unavailable; new allocations are frozen'

    def mark_accounting_unavailable(self, count=1):
        """Freeze new allocations when a scoped accounting coverage gap is material."""
        self.accounting_unavailable += max(0, int(count))
        if self.accounting_unavailable:
            self.blocked = self.blocked or 'Accounting inputs unavailable; new allocations are frozen'

    def open_position(self, signal, entry_bar, signal_id=None):
        ticker = signal['ticker']
        if self.blocked or signal['direction'] not in ('LONG', 'SHORT') or self.has_open(ticker):
            return None
        entry = signal['entry']
        if not math.isfinite(entry) or entry <= 0:
            return None
        stop, target = signal['stop'], signal['target']
        if not all(math.isfinite(v) and v > 0 for v in (stop, target)):
            return None
        if not (stop < entry < target if signal['direction'] == 'LONG' else target < entry < stop):
            return None
        if self.accounting_unavailable:
            return None
        budget = min(self.sizing_capital * self.position_pct, self.available)
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
