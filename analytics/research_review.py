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
from db.logger import ACCOUNTING_VERSION, cashflow_summary, load_cashflow_postings


ACCOUNTING_COMPONENTS = ('cash_delta', 'receivable_delta', 'payable_delta',
                         'borrow_payable_delta', 'refund_receivable_delta',
                         'repayment_liability_delta')

UNCERTAINTY = {
    'method': 'paired moving-block bootstrap',
    'block_sessions': 5,
    'draws': 2000,
    'seed': 20260918,
    'alpha': 0.05,
}


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
    required = ('manifest.json', 'bars.json', 'trades.json', 'cashflows.json', 'run.db')
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
    required_manifest = ('source', 'backend', 'account', 'feed', 'session_policy',
                         'fill_policy', 'dataset_sha256', 'accounting_version')
    missing_manifest = [key for key in required_manifest if key not in manifest]
    if missing_manifest:
        raise ValueError(f'incomplete immutable manifest for {folder}: {", ".join(missing_manifest)}')
    with sqlite3.connect(folder / 'run.db') as conn:
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'trades' not in tables:
            raise ValueError(f'journal missing trades table for {folder}')
        runs = [dict(row) for row in conn.execute('SELECT * FROM runs')]
        matching = [row for row in runs if json.loads(row['manifest_json']) == manifest]
        if len(matching) != 1:
            raise ValueError(f'journal manifest mismatch for {folder}')
        run_id = matching[0]['id']
        db_trades = [dict(row) for row in conn.execute(
            'SELECT * FROM trades WHERE run_id=? ORDER BY id', (run_id,))]
        def substantive(row):
            return {key: value for key, value in row.items()
                    if key not in {'id', 'created_at', 'regime'}}
        db_trade_content = sorted((substantive(row) for row in db_trades),
                                   key=lambda row: (row.get('entry_at') or '', row.get('ticker') or '',
                                                    row.get('signal_id') or 0))
        export_trade_content = sorted((substantive(row) for row in trades),
                                      key=lambda row: (row.get('entry_at') or '', row.get('ticker') or '',
                                                       row.get('signal_id') or 0))
        if db_trade_content != export_trade_content:
            raise ValueError(f'journal/trades content mismatch for {folder}')
        db_flows = [dict(row) for row in conn.execute(
            'SELECT * FROM accounting_postings WHERE run_id=? AND source=? AND backend=? '
            'AND account=? AND accounting_version=? ORDER BY occurred_at,id',
            (run_id, manifest['source'], manifest['backend'], manifest['account'],
             manifest['accounting_version']))] if 'accounting_postings' in tables else []
        if [substantive(row) for row in db_flows] != [substantive(row) for row in cashflows]:
            raise ValueError(f'journal/cashflow content mismatch for {folder}')
        conflicts = (conn.execute('SELECT count(*) FROM accounting_posting_conflicts '
                                   'WHERE run_id=?', (run_id,)).fetchone()[0]
                     if 'accounting_posting_conflicts' in tables else 0)
    summary = cashflow_summary(run_id, str(folder / 'run.db'), source=manifest['source'],
                               backend=manifest['backend'], account=manifest['account'],
                               accounting_version=manifest['accounting_version'])
    unknown = bool(conflicts or summary['unavailable_count'] or
                   summary['coverage'].get('incomplete', 0) or summary['coverage'].get('conflict', 0))
    return {'folder': str(folder), 'manifest': manifest, 'bars': bars, 'trades': trades,
            'cashflows': cashflows, 'run_id': run_id, 'accounting': summary,
            'journal': {'trades': len(trades), 'postings': len(cashflows),
                        'postings_complete': True, 'conflicts': conflicts,
                        'unknown_or_incomplete': unknown}}


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
    if block != UNCERTAINTY['block_sessions'] or draws != UNCERTAINTY['draws']:
        raise ValueError('uncertainty settings are registered and immutable')
    days = sorted(baseline)
    if set(days) != set(candidate):
        raise ValueError('Paired comparison requires matching sessions')
    delta = np.array([candidate[d] - baseline[d] for d in days])
    if len(delta) < 2 * block:
        return {'mean_delta': float(delta.mean()), 'interval': None, 'reason': 'insufficient_sessions'}
    rng = np.random.default_rng(UNCERTAINTY['seed'])
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
    registered = protocol.get('acceptance', {})
    registered_min = registered.get('minimum_sessions', min_sessions)
    if min_sessions != registered_min:
        raise ValueError('minimum session criterion is registered and immutable')
    windows = {w['name']: w for w in protocol.get('windows', [])}
    holdout_names = {name for name, w in windows.items() if w.get('role') == 'holdout'}
    holdout = [r for r in rows if r['window'] in holdout_names]
    sessions = min((len(r['marked']['marked_pnl_by_session']) for r in holdout), default=0)
    reasons = []
    if not limits:
        reasons.append('risk limits are unset')
    if protocol.get('registered_collection') is not True:
        reasons.append('registered collection is not complete')
    coverage = protocol.get('accounting_coverage', {})
    if coverage.get('status') != 'complete':
        reasons.append('accounting coverage is not established as complete')
    if not any((r.get('accounting_coverage', {}).get('verified', 0) or
                r.get('accounting_coverage', {}).get('scenario', 0)) > 0 for r in rows):
        reasons.append('accounting coverage has no positive verified or scenario evidence')
    if sessions < min_sessions:
        reasons.append(f'insufficient independent sessions ({sessions} < {min_sessions})')
    if any(r['marked']['cash_equity_status'] != 'reconciled' or
           r.get('accounting_claim_allowed') is False for r in rows):
        reasons.append('accounting is not fully reconciled')
    if any(not r.get('journal_postings_complete', True) or
           r.get('journal_unknown_or_incomplete', False) for r in rows):
        reasons.append('accounting posting exports are incomplete')
    candidates = [r for r in holdout if r['variant'] != 'baseline']
    harmful = any((r['paired_session_comparison'].get('interval') or [0, 0])[1] < 0
                  and r['expectancy_per_trade'] is not None and r['expectancy_per_trade'] < 0
                  for r in candidates)
    favorable = bool(candidates) and all(
        r['expectancy_per_trade'] is not None and r['expectancy_per_trade'] > 0 and
        (r['paired_session_comparison'].get('interval') or [0, 0])[0] > 0
        for r in candidates)
    risk_ok = True
    for row in holdout:
        marked = row['marked']
        for key, limit in (('max_marked_drawdown', limits.get('max_drawdown') if limits else None),
                           ('max_gross_exposure', limits.get('max_gross_exposure') if limits else None),
                           ('turnover_over_starting_capital', limits.get('max_turnover') if limits else None)):
            if limit is not None and marked.get(key, float('inf')) > limit:
                reasons.append(f'{key} exceeds registered risk limit')
                risk_ok = False
    incomplete = any('accounting' in reason or 'registered collection' in reason
                      or 'risk limits are unset' in reason for reason in reasons)
    if favorable and sessions >= registered_min and not reasons and risk_ok and not incomplete:
        status = 'keep'
    elif harmful and not reasons:
        status = 'reject'
    else:
        status = 'inconclusive'
    if status == 'keep':
        reasons.append('all registered keep criteria passed')
    elif status == 'reject':
        reasons.append('registered reject criteria: negative expectancy and paired interval')
    return {'status': status, 'promotable': status == 'keep', 'reasons': reasons,
            'risk_limits': limits, 'sessions_observed': sessions,
            'minimum_sessions': registered_min,
            'criteria': registered}


def review(root, *, min_sessions=60):
    root = Path(root)
    comparison = json.loads((root / 'comparison.json').read_text())
    protocol = json.loads((root / 'protocol.json').read_text()) if (root / 'protocol.json').exists() else {}
    if not protocol:
        raise ValueError('registered protocol.json is required')
    registered_trials = protocol.get('registered_trials')
    observed_trials = {(r['window']['name'], r['variant']) for r in comparison}
    if registered_trials is not None:
        expected_trials = {(r['window'], r['variant']) for r in registered_trials}
        if observed_trials != expected_trials:
            raise ValueError('comparison does not contain the registered trial inventory')
    output = root / 'marked-review.json'
    if output.exists():
        raise ValueError('Review already exists; preserve the saved results')
    results = []
    artifacts = []
    expected_policy = None
    expected_population = protocol.get('population_fingerprint')
    uncertainty = protocol.get('uncertainty', {})
    for key in ('method', 'block_sessions', 'draws', 'seed'):
        if uncertainty.get(key) != UNCERTAINTY[key]:
            raise ValueError(f'uncertainty setting {key} is not frozen to the registered protocol')
    window_dataset_hashes = {}
    for row in comparison:
        folder = root / row['window']['name'] / row['variant']
        artifact = verify_artifact(folder)
        manifest = artifact['manifest']
        if expected_population and manifest.get('population_fingerprint') != expected_population:
            raise ValueError(f'registered population mismatch for {folder}')
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
        accounting_allowed = (not artifact['journal']['unknown_or_incomplete'] and
                              marked['cash_equity_status'] == 'reconciled')
        basis = 'fully_accounted_net_cost_and_cashflow_basis' if accounting_allowed else 'unknown_accounting_basis'
        marked['accounting_basis'] = basis
        results.append({'window': row['window']['name'], 'role': row['window'].get('role'),
                        'variant': row['variant'], 'marked': marked,
                        'expectancy_per_trade': (sum(float(t.get('pnl') or 0) for t in closed) / len(closed)
                                                 if closed else None),
                        'expectancy_basis': basis,
                        'accounting_coverage': artifact['accounting']['coverage'],
                        'accounting_basis': basis,
                        'accounting_claim_allowed': accounting_allowed,
                        'absolute_profitability': {'marked_net_pnl': marked['marked_net_pnl'],
                                                   'closed_net_pnl': sum(float(t.get('pnl') or 0) for t in closed),
                                                   'profitable': (marked['marked_net_pnl'] > 0
                                                                  if accounting_allowed else None)},
                        'subgroups': {'basis': basis, **_subgroups(trades)},
                        'concentration': {'basis': basis, 'ticker_abs_pnl_share': {
                            key: (abs(value['net_pnl']) / total_abs if total_abs else None)
                            for key, value in concentration.items()}},
                        'excluded_or_incomplete': {
                            'censored_positions': row.get('censored_positions', 0),
                            'pending_candidates': row.get('diagnostics', {}).get('pending_candidates', 0),
                            'accounting_unavailable': marked['accounting_unavailable_count'],
                            'journal_conflicts': artifact['journal']['conflicts']},
                        'removal': {'basis': basis,
                                    'without_best_session': marked['marked_net_pnl'] - max(marked['marked_pnl_by_session'].values(), default=0)}})
        results[-1]['journal_postings_complete'] = artifact['journal']['postings_complete']
        results[-1]['journal_unknown_or_incomplete'] = artifact['journal']['unknown_or_incomplete']
    for row in results:
        baseline = next(r for r in results if r['window'] == row['window'] and r['variant'] == 'baseline')
        row['paired_session_comparison'] = paired_interval(
            row['marked']['marked_pnl_by_session'], baseline['marked']['marked_pnl_by_session'])
    decision = _decision(results, protocol, min_sessions=min_sessions)
    report = {'schema_version': 2, 'status': decision['status'], 'decision': decision,
              'uncertainty': {**UNCERTAINTY, 'frozen': True,
                              'comparison': 'paired interval per variant versus baseline'},
              'policy': {'candidate_feed_calendar': expected_policy,
                         'all_trials_retained': True},
              'trials': results}
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    memo = [f'# Registered review decision: {decision["status"]}', '',
            'This memo is generated from the immutable artifacts after checksum and journal reconciliation.', '',
            f'Criteria: minimum independent sessions = {decision["minimum_sessions"]}; '
            'positive net expectancy and a paired interval wholly above zero are required to keep.',
            'A negative net expectancy with a paired interval wholly below zero is a reject. '
            'Unset risk limits, incomplete accounting, or insufficient sessions produce inconclusive.', '',
            'Reasons:', *[f'- {reason}' for reason in decision['reasons']], '']
    (root / 'decision-memo.md').write_text('\n'.join(memo))
    print(f'Saved {output}')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison', required=True)
    review(p.parse_args().comparison)
