"""Fixed gate comparisons on predeclared chronological windows; no threshold search."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import pandas as pd
import config
from backtest import normalize_bars, run_portfolio, export_result
from db.logger import _connect
from signals.quality import ResearchGate, POLICY
from data.sessions import calendar, session_bounds, utc
from analytics.metrics import CLOSED, compute_metrics
from analytics.research_review import review

# Preserve the historical module API while exposing the bounded shadow submodule.
__path__ = [str(Path(__file__).with_name('research'))]


def validate_windows(windows):
    previous = None
    holdout_seen = False
    names = set()
    if not windows:
        raise ValueError('At least one development and one holdout window are required')
    for w in windows:
        start, end = utc(w['start']), utc(w['end'])
        name = w['name']
        if (not name or name in ('.', '..') or '/' in name or '\\' in name or name in names
                or pd.isna(start) or pd.isna(end) or start >= end
                or (previous is not None and start < previous)
                or w['role'] not in ('development', 'holdout')
                or (holdout_seen and w['role'] == 'development')):
            raise ValueError('Windows need unique safe names, chronological nonoverlap, development before holdout')
        names.add(name)
        holdout_seen |= w['role'] == 'holdout'
        previous = end
    if {w['role'] for w in windows} != {'development', 'holdout'}:
        raise ValueError('Both development and holdout windows are required')


def window_sessions(w):
    start, end = utc(w['start']), utc(w['end'])
    days = set()
    for year in range(start.year, end.year + 1):
        for d in calendar(year).sessions:
            day = str(d.date())
            opening, closing = session_bounds(day + 'T17:00Z')
            if opening < end and closing > start:
                days.add(day)
    return sorted(days)


def diagnostics(result, db, w):
    with _connect(db) as conn:
        signals = [dict(r) for r in conn.execute(
            'SELECT ticker,direction,skip_reason,gate_json FROM signals WHERE run_id=?', (result['run_id'],))]
    reasons, checks = Counter(), Counter()
    for s in signals:
        reasons[s['skip_reason'] or 'eligible'] += 1
        if s['gate_json']:
            detail = json.loads(s['gate_json'])
            checks['accepted' if detail['accepted'] else 'rejected'] += 1
            for name, check in detail['checks'].items():
                checks[name + ':' + check['reason']] += 1
    closed = [t for t in result['trades'] if t['outcome'] in CLOSED]
    daily = dict.fromkeys(window_sessions(w), 0.0)
    for t in closed:
        day = str(utc(t['exit_at']).tz_convert('America/New_York').date())
        daily[day] = daily.get(day, 0.0) + t['pnl']
    total = sum(daily.values())
    tickers = result['metrics']['by_ticker']
    expected = window_sessions(w)
    observed_by_symbol = {
        symbol: {str(utc(r['timestamp']).tz_convert('America/New_York').date()) for r in rows}
        for symbol, rows in result['dataset'].items()}
    observed = sorted(set.intersection(*observed_by_symbol.values())) if observed_by_symbol else []
    incomplete = sorted(set(expected) - set(observed))
    return {
        'sessions': len(daily), 'closed_net_pnl_by_exit_session': daily,
        'session_inventory': {'expected': expected, 'observed': observed,
                              'incomplete': incomplete,
                              'eligible': sorted(set(expected) - set(incomplete))},
        'net_pnl_per_session': total / len(daily) if daily else None,
        'net_pnl_without_best_session': total - max(daily.values(), default=0),
        'net_pnl_without_best_ticker': total - max((b['pnl'] for b in tickers.values()), default=0),
        'signal_execution_reasons': dict(reasons), 'candidate_gate_checks': dict(checks),
        'by_side': {side: compute_metrics([t for t in closed if t['direction'] == side]) for side in ('LONG', 'SHORT')},
        'by_asset_group': {name: compute_metrics([t for t in closed if (t['ticker'] in ('SPY', 'QQQ')) == etf])
                           for name, etf in (('stocks', False), ('SPY_QQQ', True))},
        'pending_candidates': result['pending_candidates'],
        'adverse_cost_loss': None,
        'adverse_cost_loss_status': 'not_supplied; run a separately registered adverse-cost artifact',
        'stale_data_fraction': (len(incomplete) / len(expected) if expected else None),
        'stale_data_status': 'fraction of expected exchange sessions with no observed bars',
        'limitations': ['P&L and drawdown are realized-only; open positions are censored, not marked to market.',
                       'Window portfolios start flat; history before start only warms features.',
                       'Gate counts include directional candidates blocked by portfolio/session state.',
                       'No statistical significance or promotion decision is inferred from this report.'],
    }


def run_comparison(dataset, windows_path, output, allow_synthetic=False, allow_zero_costs=False):
    dataset, windows_path, output = Path(dataset), Path(windows_path), Path(output)
    windows = json.loads(windows_path.read_text())
    validate_windows(windows)
    meta_path = dataset.with_suffix('.meta.json')
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    feed = meta.get('feed', 'saved:unknown provenance')
    if not allow_synthetic and ('synthetic' in feed.lower() or 'unknown' in feed.lower() or feed == 'fixture'):
        raise ValueError('Market-data feed provenance required; --allow-synthetic is for correctness checks only')
    if not allow_zero_costs and not any((config.SPREAD_BPS, config.SLIPPAGE_BPS, config.FEE_PER_SHARE)):
        raise ValueError('Declare nonzero modeled costs, or explicitly use --allow-zero-costs for a frictionless check')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty; preserve prior experiment records')
    bars = {s: normalize_bars(pd.DataFrame(rows)) for s, rows in json.loads(dataset.read_text()).items()}
    if 'SPY' not in bars or not any(s != 'SPY' for s in bars):
        raise ValueError('Comparison requires SPY and at least one other symbol')
    coverage = {}
    for w in windows:
        start, end = utc(w['start']), utc(w['end'])
        coverage[w['name']] = {}
        expected_sessions = window_sessions(w)
        for s, df in bars.items():
            selected = df[(df.timestamp >= start) & (df.timestamp < end)]
            if selected.empty:
                raise ValueError(f'No evaluation bars for {s} in {w["name"]}')
            if any((t - session_bounds(t)[0]) % pd.Timedelta(minutes=5) != pd.Timedelta(0) for t in df.timestamp):
                raise ValueError('Expected exchange-aligned five-minute bar start timestamps')
            observed_sessions = sorted(selected.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d').unique())
            coverage[w['name']][s] = {'bars': len(selected), 'sessions': len(observed_sessions),
                                      'observed_sessions': observed_sessions,
                                      'expected_sessions': expected_sessions,
                                      'incomplete_sessions': sorted(set(expected_sessions) - set(observed_sessions)),
                                      'warmup_bars': int((df.timestamp < start).sum())}
    output.mkdir(parents=True, exist_ok=True)
    population_fingerprint = hashlib.sha256(json.dumps({
        'dataset_file_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
        'windows': windows, 'policy': POLICY,
    }, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    protocol = {'dataset_file_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
                'dataset_metadata': meta, 'windows': windows, 'policy': POLICY,
                'population_fingerprint': population_fingerprint,
                'coverage': coverage, 'costs': {'spread_bps': config.SPREAD_BPS,
                    'slippage_bps_per_fill': config.SLIPPAGE_BPS, 'fee_per_share_per_fill': config.FEE_PER_SHARE},
                'primary_comparison': 'fully accounted marked net P&L per exchange session versus baseline',
                'uncertainty': {'method': 'paired moving-block bootstrap', 'block_sessions': 5,
                                'draws': 2000, 'seed': 20260918, 'frozen': True},
                'risk_limits': None,
                'registered_collection': False,
                'accounting_coverage': {'status': 'unregistered', 'reason': 'registered journal coverage is required'},
                'registered_trials': [{'window': w['name'], 'variant': mode}
                                     for w in windows for mode in ('baseline', 'strength', 'rvol', 'both')],
                'acceptance': {'minimum_sessions': 60,
                               'keep': ['positive net expectancy',
                                        'paired interval lower bound above zero'],
                               'reject': ['negative net expectancy',
                                          'paired interval upper bound below zero'],
                               'risk_limits_required_for_promotion': True},
                'all_trials_retained': True,
                'promotion': 'inconclusive; inspect censoring, marked exposure, sample adequacy and cost sensitivity before promotion',
                'allow_synthetic': allow_synthetic, 'allow_zero_costs': allow_zero_costs}
    (output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    summary = []
    indicator_cache = {}  # Reuse only within these fixed bars and unchanged settings.
    for w in windows:
        start, end = utc(w['start']), utc(w['end'])
        subset = {s: df[df.timestamp < end] for s, df in bars.items()}
        for mode in ('baseline', 'strength', 'rvol', 'both'):
            dest = output / w['name'] / mode
            dest.mkdir(parents=True)
            result = run_portfolio(subset, str(dest / 'run.db'), feed=feed,
                gate=ResearchGate(subset, mode), gate_name=mode, evaluation_start=start, indicator_cache=indicator_cache,
                metadata={'window': w, 'quality_policy': POLICY, 'dataset_metadata': meta,
                          'input_dataset_sha256': protocol['dataset_file_sha256'],
                          'population_fingerprint': population_fingerprint})
            export_result(result, dest)
            detail = diagnostics(result, str(dest / 'run.db'), w)
            (dest / 'diagnostics.json').write_text(json.dumps(detail, indent=2, allow_nan=False) + '\n')
            summary.append({'window': w, 'variant': mode, 'metrics': result['metrics'],
                            'diagnostics': detail, 'censored_positions': result['censored_positions']})
            print(f'{w["name"]}/{mode}: {result["metrics"]["n_closed"]} closed trades', flush=True)
    (output / 'comparison.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    lines = ['# Gate comparison', '', 'Status: exploratory; no candidate promoted.', '',
             f'Feed: {feed}. Costs: {protocol["costs"]}.', '',
             '| Window | Variant | Closed | Net P&L | Net/session | Δ/session vs baseline | Realized drawdown | Open |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    baselines = {r['window']['name']: r['diagnostics']['net_pnl_per_session'] for r in summary if r['variant'] == 'baseline'}
    for r in summary:
        m, d = r['metrics'], r['diagnostics']
        lines.append(f'| {r["window"]["name"]} | {r["variant"]} | {m["n_closed"]} | {m["total_pnl"]:.2f} | '
                     f'{d["net_pnl_per_session"]:.2f} | {d["net_pnl_per_session"] - baselines[r["window"]["name"]]:.2f} | '
                     f'{m["max_drawdown"]:.2f} | {r["censored_positions"]} |')
    lines += ['', 'Synthetic fixtures establish correctness only. Missing or rejected context is recorded in diagnostics.json.',
              'Realized results omit open-position value and risk. Inspect coverage, censoring and per-session/ticker/side breakdowns.',
              'Costs are declared scenarios, not measured spreads. Run adverse costs in a separate output directory.',
              'This report does not supply marked-to-market exposure, session-block uncertainty, or a promotion decision.']
    (output / 'comparison.md').write_text('\n'.join(lines) + '\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset')
    p.add_argument('--windows', help='JSON list of {name,start,end,role:development|holdout}')
    p.add_argument('--output')
    p.add_argument('--review', help='Review an existing comparison directory and write marked-review.json')
    p.add_argument('--min-sessions', type=int, default=60)
    p.add_argument('--allow-synthetic', action='store_true')
    p.add_argument('--allow-zero-costs', action='store_true')
    args = p.parse_args()
    if args.review:
        review(args.review, min_sessions=args.min_sessions)
    elif not (args.dataset and args.windows and args.output):
        p.error('--dataset, --windows and --output are required unless --review is used')
    else:
        run_comparison(args.dataset, args.windows, args.output, args.allow_synthetic, args.allow_zero_costs)


if __name__ == '__main__':
    main()
