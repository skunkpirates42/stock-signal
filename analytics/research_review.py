"""Post-replay marked equity/exposure and paired session-block uncertainty.

Accounting supplement only: no entry/exit policy or strategy selection changes.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.sessions import utc


def marked_metrics(trades, bars, start, end, capital=100000):
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
    peaks = np.maximum.accumulate(np.r_[capital, equity])[1:]
    drawdown = peaks - equity
    days = pd.Index(idx.tz_convert('America/New_York').date.astype(str))
    daily_equity = pd.Series(equity, index=days).groupby(level=0).last()
    daily_pnl = daily_equity.diff()
    daily_pnl.iloc[0] = daily_equity.iloc[0] - capital
    realized = sum(t.get('pnl') or 0 for t in trades)
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
        'valuation_policy': 'Latest observed completed close; forward-fill only, entry costs deducted; no hypothetical exit cost.',
        'limitations': ['Excludes dividend cash flows, short borrow fees and taxes.',
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


def review(root):
    root = Path(root)
    comparison = json.loads((root / 'comparison.json').read_text())
    output = root / 'marked-review.json'
    if output.exists():
        raise ValueError('Review already exists; preserve the saved results')
    results = []
    for row in comparison:
        folder = root / row['window']['name'] / row['variant']
        trades = json.loads((folder / 'trades.json').read_text())
        bars = json.loads((folder / 'bars.json').read_text())
        manifest = json.loads((folder / 'manifest.json').read_text())
        marked = marked_metrics(trades, bars, row['window']['start'], row['window']['end'], manifest['settings']['STARTING_CAPITAL'])
        results.append({'window': row['window']['name'], 'variant': row['variant'], 'marked': marked})
    for row in results:
        baseline = next(r for r in results if r['window'] == row['window'] and r['variant'] == 'baseline')
        row['paired_session_comparison'] = paired_interval(row['marked']['marked_pnl_by_session'], baseline['marked']['marked_pnl_by_session'])
    output.write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
    print(f'Saved {output}')
    return results


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison', required=True)
    review(p.parse_args().comparison)
