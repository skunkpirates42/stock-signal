"""Post-replay marked equity/exposure and paired session-block uncertainty.

Accounting supplement only: no entry/exit policy or strategy selection changes.
"""
import argparse
import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from data.sessions import utc
from analytics.metrics import CLOSED


ACCOUNTING_COMPONENTS = ('cash_delta', 'receivable_delta', 'payable_delta',
                         'borrow_payable_delta', 'refund_receivable_delta',
                         'repayment_liability_delta')


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_dataset_hash(bars):
    """Match ``backtest.manifest_for`` without importing replay code."""
    canonical = {symbol: [{**row, 'timestamp': utc(row['timestamp']).isoformat()}
                          for row in rows]
                 for symbol, rows in sorted(bars.items())}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def verify_artifact(folder):
    """Validate one immutable replay directory before using any result in a report."""
    folder = Path(folder)
    required = ('manifest.json', 'bars.json', 'trades.json', 'run.db')
    missing = [name for name in required if not (folder / name).exists()]
    if missing:
        raise ValueError(f'incomplete result artifact {folder}: missing {", ".join(missing)}')
    manifest = json.loads((folder / 'manifest.json').read_text())
    bars = json.loads((folder / 'bars.json').read_text())
    trades = json.loads((folder / 'trades.json').read_text())
    cashflow_path = folder / 'cashflows.json'
    cashflows = json.loads(cashflow_path.read_text()) if cashflow_path.exists() else []
    if manifest.get('dataset_sha256') != _canonical_dataset_hash(bars):
        raise ValueError(f'checksum mismatch for {folder}/bars.json')
    if manifest.get('symbols') and sorted(manifest['symbols']) != sorted(bars):
        raise ValueError(f'symbol manifest mismatch for {folder}')
    metadata = folder / 'bars.meta.json'
    if metadata.exists():
        feed = json.loads(metadata.read_text()).get('feed')
        if feed != manifest.get('feed'):
            raise ValueError(f'feed manifest mismatch for {folder}')
    with sqlite3.connect(folder / 'run.db') as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'trades' not in tables:
            raise ValueError(f'journal missing trades table for {folder}')
        db_trade_count = conn.execute('SELECT count(*) FROM trades').fetchone()[0]
        if db_trade_count != len(trades):
            raise ValueError(f'journal/trades mismatch for {folder}')
        db_flow_count = (conn.execute('SELECT count(*) FROM accounting_postings').fetchone()[0]
                         if 'accounting_postings' in tables else 0)
        if cashflow_path.exists() and db_flow_count != len(cashflows):
            raise ValueError(f'journal/cashflow mismatch for {folder}')
        conflicts = (conn.execute('SELECT count(*) FROM accounting_posting_conflicts').fetchone()[0]
                     if 'accounting_posting_conflicts' in tables else 0)
    return {'folder': str(folder), 'manifest': manifest, 'bars': bars, 'trades': trades,
            'cashflows': cashflows, 'journal': {'trades': len(trades), 'postings': len(cashflows),
                                                'postings_complete': cashflow_path.exists(),
                                                'conflicts': conflicts}}


def _decimal(value):
    return Decimal(str(value or 0))


def _accounting_equity_series(cashflows, idx):
    """Return the contract's cash-plus-balance equity overlay at each mark.

    A payment changes cash and discharges its matched balance, so its net overlay is
    zero.  This makes a settlement a cash movement rather than a second item of income.
    """
    states = {component: Decimal('0') for component in ACCOUNTING_COMPONENTS}
    unavailable = 0
    rows = []
    seen = set()
    for sequence, flow in enumerate(cashflows):
        key = flow.get('logical_key')
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        if flow.get('unavailable_reason'):
            unavailable += 1
            continue
        occurred = flow.get('occurred_at', flow.get('timestamp'))
        if occurred is None:
            raise ValueError('accounting flow requires occurred_at')
        rows.append((utc(occurred), sequence, flow))
    rows.sort(key=lambda row: (row[0], row[1]))
    values = []
    cursor = 0
    for timestamp in idx:
        while cursor < len(rows) and rows[cursor][0] <= timestamp:
            for component in ACCOUNTING_COMPONENTS:
                states[component] += _decimal(rows[cursor][2].get(component, 0))
            cursor += 1
        values.append(float(states['cash_delta'] + states['receivable_delta']
                            + states['refund_receivable_delta'] - states['payable_delta']
                            - states['borrow_payable_delta'] - states['repayment_liability_delta']))
    return np.asarray(values), states, unavailable


def _cash_principal_equity_series(trades, marks, idx, capital):
    """Reconstruct legacy marked equity from trade cash, marks, fees and rounding.

    Saved ``pnl`` remains authoritative for older rows.  The explicit bridge captures
    its difference from reconstructible principal/fee arithmetic rather than silently
    misclassifying an old rounding or missing-fee difference as accounting income.
    """
    cash = np.full(len(idx), float(capital))
    market_value = np.zeros(len(idx))
    rounding_bridge = np.zeros(len(idx))
    cost_evidence_complete = True
    for trade in trades:
        entry_at = utc(trade['entry_at'])
        exit_at = utc(trade['exit_at']) if trade.get('exit_at') else None
        sign = 1 if trade['direction'] == 'LONG' else -1
        shares = float(trade['shares'])
        entry = float(trade['entry'])
        entry_cost = float(trade.get('entry_cost') or 0)
        entered = idx >= entry_at
        cash[entered] -= sign * entry * shares + entry_cost
        active = entered & ((idx < exit_at) if exit_at is not None else True)
        price = marks[trade['ticker']].to_numpy(dtype=float)
        if np.isnan(price[active]).any():
            raise ValueError('Position lacks a causal valuation price')
        market_value[active] += sign * price[active] * shares
        if exit_at is None:
            continue
        if trade.get('exit_price') is None or trade.get('pnl') is None:
            raise ValueError('Closed trade lacks price or saved P&L for cash reconciliation')
        exit_price = float(trade['exit_price'])
        if trade.get('costs') is None:
            # A saved net P&L is still used by the marked legacy series, but absent
            # execution-cost detail leaves the cash/principal reconstruction unknown.
            # Do not hide that gap inside a balancing residual.
            cost_evidence_complete = False
            costs = entry_cost
        else:
            costs = float(trade['costs'])
        exit_cost = costs - entry_cost
        closed = idx >= exit_at
        cash[closed] += sign * exit_price * shares - exit_cost
        gross = sign * (exit_price - entry) * shares
        bridge = float(trade['pnl']) - (gross - costs)
        rounding_bridge[closed] += bridge
    return cash + market_value + rounding_bridge, cost_evidence_complete


def marked_metrics(trades, bars, start, end, capital=100000, cashflows=()):
    prices = {}
    for symbol, rows in bars.items():
        df = pd.DataFrame(rows)
        index = pd.to_datetime(df.timestamp, utc=True) + pd.Timedelta(minutes=5)
        prices[symbol] = pd.Series(df.close.to_numpy(dtype=float), index=index)
    marks = pd.DataFrame(prices).sort_index().ffill()
    # Replay windows select bar starts, so the final completed mark can equal end.
    marks = marks[(marks.index > utc(start)) & (marks.index <= utc(end))]
    if marks.empty:
        raise ValueError('No valuation observations in window')
    idx = marks.index
    equity = np.full(len(idx), float(capital))
    exposure = np.zeros(len(idx))
    turnover = 0.0
    for trade in trades:
        entry_at = utc(trade['entry_at'])
        exit_at = utc(trade['exit_at']) if trade.get('exit_at') else None
        active = (idx >= entry_at) & ((idx < exit_at) if exit_at is not None else True)
        sign = 1 if trade['direction'] == 'LONG' else -1
        shares = trade['shares']
        price = marks[trade['ticker']].to_numpy()
        if np.isnan(price[active]).any():
            raise ValueError('Position lacks a causal valuation price')
        equity[active] += sign * (price[active] - trade['entry']) * shares - (trade.get('entry_cost') or 0)
        exposure[active] += price[active] * shares
        turnover += trade['entry'] * shares
        if exit_at is not None:
            equity[idx >= exit_at] += trade['pnl']
            turnover += trade['exit_price'] * shares
    accounting_overlay, accounting_balances, unavailable = _accounting_equity_series(cashflows, idx)
    equity += accounting_overlay
    cash_principal_equity, cost_evidence_complete = _cash_principal_equity_series(trades, marks, idx, capital)
    reconciliation_error = (float(np.max(np.abs(equity - (cash_principal_equity + accounting_overlay))))
                            if cost_evidence_complete else None)
    peaks = np.maximum.accumulate(np.r_[capital, equity])[1:]
    drawdown = peaks - equity
    days = pd.Index(idx.tz_convert('America/New_York').date.astype(str))
    daily_equity = pd.Series(equity, index=days).groupby(level=0).last()
    daily_pnl = daily_equity.diff()
    daily_pnl.iloc[0] = daily_equity.iloc[0] - capital
    realized = sum(t.get('pnl') or 0 for t in trades)
    accounting_equity_delta = float(accounting_overlay[-1])
    return {
        'ending_marked_equity': float(equity[-1]), 'marked_net_pnl': float(equity[-1] - capital),
        'open_position_net_contribution': float(equity[-1] - capital - realized),
        'max_marked_drawdown': float(drawdown.max()),
        'max_marked_drawdown_pct': float(np.max(drawdown / peaks)),
        'max_gross_exposure': float(exposure.max()),
        'mean_gross_exposure_at_observations': float(exposure.mean()),
        'traded_notional': float(turnover), 'turnover_over_starting_capital': float(turnover / capital),
        'marked_net_per_session': float(daily_pnl.mean()),
        'marked_pnl_by_session': {str(k): float(v) for k, v in daily_pnl.items()},
        'accounting_equity_delta': accounting_equity_delta,
        'accounting_balances': {key: format(value, 'f') for key, value in accounting_balances.items()},
        'accounting_unavailable_count': unavailable,
        'cash_equity_max_error': reconciliation_error,
        'cash_equity_reconciles': bool(cost_evidence_complete and reconciliation_error <= 1e-8),
        'cash_equity_status': 'reconciled' if cost_evidence_complete and reconciliation_error <= 1e-8
                               else ('mismatch' if cost_evidence_complete else 'unknown_execution_costs'),
        'valuation_policy': 'Latest observed completed close; forward-fill only, entry costs deducted; no hypothetical exit cost.',
        'limitations': ['Cash-flow inputs are included only when explicitly supplied; historical action and borrow coverage may be incomplete.',
                       'Marks use IEX observations; missing observations can produce stale marks.',
                       'Exposure mean weights observations equally, not overnight elapsed time.']}


def paired_interval(candidate, baseline, block=5, draws=2000):
    days = sorted(baseline)
    if set(days) != set(candidate):
        raise ValueError('Paired comparison requires matching sessions')
    delta = np.array([candidate[d] - baseline[d] for d in days])
    if len(delta) < 2 * block:
        return {'mean_delta': float(delta.mean()), 'interval': None, 'reason': 'insufficient_sessions'}
    rng = np.random.default_rng(20260918)
    starts = rng.integers(0, len(delta) - block + 1, size=(draws, int(np.ceil(len(delta) / block))))
    sampled = delta[(starts[:, :, None] + np.arange(block)).reshape(draws, -1)[:, :len(delta)]]
    low, high = np.quantile(sampled.mean(axis=1), [.025, .975])
    return {'mean_delta': float(delta.mean()), 'interval': [float(low), float(high)],
            'method': 'paired moving-block bootstrap, 5 sessions, 2000 draws, seed 20260918; descriptive, unadjusted for variant selection'}


def _subgroups(trades):
    closed = [t for t in trades if t.get('outcome') in ('WIN', 'LOSS', 'BREAKEVEN')]
    def group(key):
        result = {}
        for trade in closed:
            name = key(trade)
            row = result.setdefault(name, {'n': 0, 'net_pnl': 0.0})
            row['n'] += 1
            row['net_pnl'] += float(trade.get('pnl') or 0)
        for row in result.values():
            row['net_pnl'] = round(row['net_pnl'], 8)
            row['expectancy_per_trade'] = row['net_pnl'] / row['n'] if row['n'] else None
        return result
    return {'side': group(lambda t: t.get('direction', 'UNKNOWN')),
            'ticker': group(lambda t: t.get('ticker', 'UNKNOWN')),
            'regime': group(lambda t: t.get('regime') or 'UNKNOWN')}


def _decision(rows, protocol, min_sessions=60):
    limits = protocol.get('risk_limits') or protocol.get('acceptance', {}).get('risk_limits')
    sessions = max((len(r['marked']['marked_pnl_by_session']) for r in rows), default=0)
    reasons = []
    if not limits:
        reasons.append('risk limits are unset')
    if sessions < min_sessions:
        reasons.append(f'insufficient independent sessions ({sessions} < {min_sessions})')
    if any(r['marked']['cash_equity_status'] != 'reconciled' for r in rows):
        reasons.append('accounting is not fully reconciled')
    if any(not r.get('journal_postings_complete', True) for r in rows):
        reasons.append('accounting posting exports are incomplete')
    return {'status': 'inconclusive', 'promotable': False, 'reasons': reasons,
            'risk_limits': limits, 'sessions_observed': sessions,
            'minimum_sessions': min_sessions}


def review(root, *, min_sessions=60):
    root = Path(root)
    comparison = json.loads((root / 'comparison.json').read_text())
    protocol = json.loads((root / 'protocol.json').read_text()) if (root / 'protocol.json').exists() else {}
    output = root / 'marked-review.json'
    if output.exists():
        raise ValueError('Review already exists; preserve the saved results')
    results = []
    artifacts = []
    expected_policy = None
    window_dataset_hashes = {}
    for row in comparison:
        folder = root / row['window']['name'] / row['variant']
        artifact = verify_artifact(folder)
        manifest = artifact['manifest']
        policy = (manifest.get('fill_policy'), manifest.get('session_policy'), manifest.get('feed'))
        dataset_hash = manifest.get('dataset_sha256')
        if expected_policy is None:
            expected_policy = policy
        elif policy != expected_policy:
            raise ValueError(f'candidate/feed/calendar policy mismatch for {folder}')
        window_name = row['window']['name']
        prior_hash = window_dataset_hashes.setdefault(window_name, dataset_hash)
        if prior_hash != dataset_hash:
            raise ValueError(f'candidate population mismatch for {folder}')
        artifacts.append(artifact)
    for row in comparison:
        folder = root / row['window']['name'] / row['variant']
        artifact = next(a for a in artifacts if a['folder'] == str(folder))
        trades, bars, manifest = artifact['trades'], artifact['bars'], artifact['manifest']
        cashflows_file = folder / 'cashflows.json'
        cashflows = json.loads(cashflows_file.read_text()) if cashflows_file.exists() else ()
        marked = marked_metrics(trades, bars, row['window']['start'], row['window']['end'],
                                manifest['settings']['STARTING_CAPITAL'], cashflows)
        closed = [t for t in trades if t.get('outcome') in CLOSED]
        concentration = _subgroups(trades)['ticker']
        total_abs = sum(abs(float(t.get('pnl') or 0)) for t in closed)
        results.append({'window': row['window']['name'], 'variant': row['variant'], 'marked': marked,
                        'expectancy_per_trade': (sum(float(t.get('pnl') or 0) for t in closed) / len(closed)
                                                 if closed else None),
                        'absolute_profitability': {'marked_net_pnl': marked['marked_net_pnl'],
                                                   'closed_net_pnl': sum(float(t.get('pnl') or 0) for t in closed),
                                                   'profitable': marked['marked_net_pnl'] > 0},
                        'subgroups': _subgroups(trades),
                        'concentration': {'ticker_abs_pnl_share': {
                            key: (abs(value['net_pnl']) / total_abs if total_abs else None)
                            for key, value in concentration.items()}},
                        'excluded_or_incomplete': {
                            'censored_positions': row.get('censored_positions', 0),
                            'pending_candidates': row.get('diagnostics', {}).get('pending_candidates', 0),
                            'accounting_unavailable': marked['accounting_unavailable_count'],
                            'journal_conflicts': artifact['journal']['conflicts']}})
        results[-1]['journal_postings_complete'] = artifact['journal']['postings_complete']
    for row in results:
        baseline = next(r for r in results if r['window'] == row['window'] and r['variant'] == 'baseline')
        row['paired_session_comparison'] = paired_interval(
            row['marked']['marked_pnl_by_session'], baseline['marked']['marked_pnl_by_session'])
    decision = _decision(results, protocol, min_sessions=min_sessions)
    report = {'schema_version': 1, 'status': decision['status'], 'decision': decision,
              'uncertainty': {'method': 'paired_interval per variant versus baseline',
                              'frozen': True, 'block_sessions': 5, 'draws': 2000,
                              'seed': 20260918},
              'policy': {'candidate_feed_calendar': expected_policy,
                         'all_trials_retained': True},
              'trials': results}
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(f'Saved {output}')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison', required=True)
    review(p.parse_args().comparison)
