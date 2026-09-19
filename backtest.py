"""Chronological portfolio replay. All symbols at a timestamp share one allocation cycle."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import pandas as pd
import config
from data.source import get_bars, active_source_name
from data.sessions import utc, in_regular_hours
from db.logger import (ACCOUNTING_VERSION, cashflow_summary, init_db, load_cashflow_postings,
                       record_accounting_coverage, record_cashflow_posting, replay_connection,
                       start_run, _connect)
from live.trader import LiveTrader
from trades.executor import PaperBroker
from analytics.metrics import compute_metrics, equity_curve, format_report


def normalize_bars(df):
    df = df.copy()
    required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    if any(k not in df for k in required):
        raise ValueError('Missing OHLCV columns')
    df = df[required]
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    for _, group in df[df.timestamp.duplicated(keep=False)].groupby('timestamp'):
        if len(group.drop_duplicates()) > 1:
            raise ValueError('Conflicting duplicate bar timestamps')
    df = df.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
    import numpy as np
    values = df[required[1:]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (df[['open','high','low','close']] <= 0).any().any() or (df.volume < 0).any():
        raise ValueError('Invalid OHLCV values')
    if ((df.high < df[['open','close','low']].max(axis=1)) | (df.low > df[['open','close','high']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC range')
    return df[df.timestamp.map(in_regular_hours)].reset_index(drop=True)


def manifest_for(bars, feed, gate='baseline'):
    canonical = {s: [{**r, 'timestamp': utc(r['timestamp']).isoformat()} for r in df.to_dict('records')]
                 for s, df in sorted(bars.items())}
    serialized = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
        diff = subprocess.check_output(['git','diff','--binary'])
    except (OSError, subprocess.CalledProcessError):
        revision, diff = 'unknown', b''
    root = Path(__file__).resolve().parent
    code_files = sorted([p for p in root.rglob('*.py') if not any(part.startswith('.') or part == 'node_modules' for part in p.relative_to(root).parts)])
    source_hash = hashlib.sha256(b''.join(str(p.relative_to(root)).encode() + p.read_bytes() for p in code_files)).hexdigest()
    times = [utc(r['timestamp']) for df in bars.values() for r in df.to_dict('records')]
    settings = {k: v for k, v in vars(config).items() if k.isupper() and isinstance(v, (int,float,str,list))
                and not any(word in k for word in ('KEY','SECRET','PATH','URL','MODEL','PROVIDER','SOUND'))}
    return {'source':'backtest', 'backend':'local', 'account':config.ACCOUNT_NAMESPACE,
            'revision':revision, 'source_sha256':source_hash, 'working_diff_sha256':hashlib.sha256(diff).hexdigest(),
            'dataset_sha256':hashlib.sha256(serialized.encode()).hexdigest(), 'feed':feed,
            'start':min(times).isoformat() if times else None, 'end':max(times).isoformat() if times else None,
            'symbols':sorted(bars), 'settings':settings, 'gate':gate,
            'fill_policy':'next_completed_5min_close', 'session_policy':config.SESSION_POLICY,
            'allocation':'exit first, alphabetical symbol order, unlevered gross exposure cap',
            'schema_version':2, 'accounting_version': ACCOUNTING_VERSION,
            'accounting_mode': 'causal_capital_rerun',
            'accounting_status': 'scenario inputs only; historical coverage is not established'}


def _accounting_event_time(event):
    timestamp = event.get('occurred_at', event.get('timestamp'))
    if timestamp is None:
        raise ValueError('accounting event requires occurred_at')
    return utc(timestamp)


def distribution_result_posting(result, occurred_at, *, prior=None, knowledge_at=None):
    """Adapt one T02 ``DistributionResult`` state transition into a ledger posting.

    This is intentionally an offline fixture/scenario seam.  It does not fetch actions,
    infer settlement timing, or turn incomplete provider evidence into a posting.  A
    multi-payment aggregate must be split by its source before calling this adapter so
    every payment retains its immutable activity identity.
    """
    prior = prior or {}
    action_key = result.action_id
    revision = result.accepted_revision
    if result.status != 'known':
        return {'event_kind': 'distribution_unavailable', 'occurred_at': occurred_at,
                'knowledge_at': knowledge_at, 'action_key': action_key, 'revision_key': revision,
                'logical_key': f'distribution:{action_key}:{result.side}:{revision}:unavailable',
                'unavailable_reason': ','.join(result.unknown_reasons) or 'unknown_distribution'}
    payments = tuple(result.included_settlements)
    if len(payments) > 1:
        raise ValueError('split T02 distribution results by immutable payment ID before posting')
    prior_settled = prior.get('settled', 0)
    settlement_delta = (result.settled or 0) - prior_settled
    cash_delta = settlement_delta if result.side == 'LONG' else -settlement_delta
    components = {
        'receivable_delta': (result.receivable or 0) - prior.get('receivable', 0),
        'payable_delta': (result.payable or 0) - prior.get('payable', 0),
        'refund_receivable_delta': (result.refund_receivable or 0) - prior.get('refund_receivable', 0),
        'repayment_liability_delta': (result.repayment_liability or 0) - prior.get('repayment_liability', 0),
    }
    allocation = f'{action_key}:{result.side}'
    # A previously observed payment can appear in a revised T02 result.  Its cash is
    # already durable, but the revision's balance correction still needs a distinct
    # posting.  Only a positive settlement delta carries the payment identity.
    payment_id = payments[0] if payments and settlement_delta else None
    return {
        'event_kind': 'distribution_settlement' if payment_id else 'distribution_accrual',
        'occurred_at': occurred_at, 'knowledge_at': knowledge_at, 'action_key': action_key,
        'revision_key': revision, 'allocation_key': allocation, 'payment_id': payment_id,
        'logical_key': None, 'cash_delta': cash_delta, **components,
    }


def borrow_result_posting(result, occurred_at, *, prior=None, knowledge_at=None):
    """Adapt one T02 ``BorrowResult`` state transition into an offline ledger posting."""
    prior = prior or {}
    charge_key = result.interval_id
    if result.status != 'known':
        return {'event_kind': 'borrow_unavailable', 'occurred_at': occurred_at,
                'knowledge_at': knowledge_at, 'action_key': charge_key,
                'logical_key': f'borrow:{charge_key}:unavailable',
                'unavailable_reason': ','.join(result.unknown_reasons) or 'unknown_borrow'}
    payments = tuple(result.included_settlements)
    if len(payments) > 1:
        raise ValueError('split T02 borrow results by immutable payment ID before posting')
    return {
        'event_kind': 'borrow_settlement' if payments else 'borrow_accrual',
        'occurred_at': occurred_at, 'knowledge_at': knowledge_at, 'action_key': charge_key,
        'allocation_key': charge_key, 'payment_id': payments[0] if payments else None,
        'logical_key': None, 'cash_delta': result.cash_delta or 0,
        'borrow_payable_delta': (result.payable or 0) - prior.get('payable', 0),
        'refund_receivable_delta': (result.refund_receivable or 0) - prior.get('refund_receivable', 0),
    }


def _accounting_available_time(event, accounting_mode):
    if accounting_mode == 'fixed_trade_restatement':
        return _accounting_event_time(event)
    known = event.get('knowledge_at')
    if known is None:
        return _accounting_event_time(event)
    return max(_accounting_event_time(event), utc(known))


def _prepare_accounting_events(events, accounting_mode):
    """Separate eventual economics from causal information availability."""
    prepared = []
    for original in events:
        event = dict(original)
        economic_at = _accounting_event_time(event)
        if accounting_mode == 'causal_capital_rerun' and event.get('knowledge_at') is None:
            # Historical process/ex-date is not decision-time knowledge.  Preserve the
            # gap as an explicit zero-value blocking event rather than treating it as
            # known at its economic date or free/irrelevant.
            event.update(
                logical_key=f"{event.get('logical_key', event.get('event_kind', 'accounting'))}:unknown-knowledge",
                unavailable_reason=event.get('unavailable_reason', 'missing_accounting_knowledge_time'),
                economic_at=economic_at.isoformat(), scheduled_at=economic_at.isoformat(),
                **{component: '0' for component in (
                    'cash_delta', 'receivable_delta', 'payable_delta', 'borrow_payable_delta',
                    'refund_receivable_delta', 'repayment_liability_delta')},
            )
        else:
            event['economic_at'] = economic_at.isoformat()
            event['scheduled_at'] = _accounting_available_time(event, accounting_mode).isoformat()
        prepared.append(event)
    return sorted(prepared, key=lambda event: (utc(event['scheduled_at']), event.get('logical_key', '')))


def _apply_accounting_events(events, through, accounting_broker, run_id, db_path):
    """Post due accounting events before the batch allocation cycle, once each."""
    applied = []
    while events and utc(events[0]['scheduled_at']) <= through:
        event = dict(events.pop(0))
        event.update(run_id=run_id, source='backtest', backend='local', account=accounting_broker.account,
                     accounting_version=ACCOUNTING_VERSION,
                     occurred_at=event['scheduled_at'])
        outcome = record_cashflow_posting(event, db_path)
        if outcome['status'] == 'inserted':
            accounting_broker.apply_accounting_posting(event)
        applied.append(outcome['status'])
    return applied


def run_portfolio(bars, db_path=None, feed='fixture', gate=None, gate_name='baseline', evaluation_start=None,
                  metadata=None, indicator_cache=None, accounting_events=(), accounting_coverage=(),
                  accounting_mode='causal_capital_rerun'):
    """Replay frozen trade rules with optional, explicitly supplied accounting scenarios.

    Cash-flow inputs are offline records.  Absence of historical actions or borrow rates
    is never treated as a zero-cost finding; callers can record the gap through
    ``accounting_coverage`` or an event carrying ``unavailable_reason``.
    """
    db_path = db_path or config.BACKTEST_DB_PATH
    bars = {s: normalize_bars(df) for s, df in bars.items()}
    if accounting_mode not in {'causal_capital_rerun', 'fixed_trade_restatement'}:
        raise ValueError('unsupported accounting mode')
    manifest = manifest_for(bars, feed, gate_name)
    manifest['accounting_mode'] = accounting_mode
    manifest.update(metadata or {})
    manifest["evaluation_start"] = str(evaluation_start) if evaluation_start else None
    init_db(db_path)
    run_id = start_run(manifest, db_path)
    broker = PaperBroker()
    # A fixed-trade restatement needs a full accounting book for reconciliation while
    # retaining every pre-existing execution decision, quantity and fill.  Its overlay
    # is therefore deliberately not the broker that sizes the replay.
    accounting_broker = broker if accounting_mode == 'causal_capital_rerun' else PaperBroker()
    trader = LiveTrader(bars, db_path=db_path, source='backtest', broker=broker, run_id=run_id, gate=gate, evaluation_start=evaluation_start, indicator_cache=indicator_cache)
    events = {}
    for s, df in bars.items():
        for bar in df.to_dict('records'):
            events.setdefault(utc(bar['timestamp']), {})[s] = bar
    pending_accounting = _prepare_accounting_events(accounting_events, accounting_mode)
    for coverage in accounting_coverage:
        record_accounting_coverage({**coverage, 'run_id': run_id, 'source': 'backtest',
                                    'backend': 'local', 'account': broker.account,
                                    'accounting_version': ACCOUNTING_VERSION}, db_path)
        if (accounting_mode == 'causal_capital_rerun'
                and coverage.get('status', 'incomplete') in {'incomplete', 'conflict'}
                and int(coverage.get('affected_count', 0)) > 0):
            accounting_broker.mark_accounting_unavailable(coverage['affected_count'])
    posting_statuses = []
    with replay_connection(db_path) as conn:
        previous_day = None
        for ts in sorted(events):
            if ts.date() != previous_day:
                conn.commit()
                previous_day = ts.date()
            # A completed bar is actionable at its close.  Accounting events at that
            # same time precede the existing exits-before-entries allocation cycle.
            posting_statuses.extend(_apply_accounting_events(
                pending_accounting, ts + pd.Timedelta(minutes=5), accounting_broker, run_id, db_path))
            trader.process_batch(events[ts])
        # Post-window events are deliberately retained as pending, not forced into the
        # window or converted into assumed settlement cash.
    with _connect(db_path) as conn:
        trades = [dict(r) for r in conn.execute('SELECT t.*, s.regime FROM trades t LEFT JOIN signals s ON s.id=t.signal_id '
                  'WHERE t.run_id=? ORDER BY t.exit_at IS NULL,t.exit_at,t.ticker,t.id', (run_id,))]
    metrics = compute_metrics(trades)
    metrics['equity'] = equity_curve(trades)
    accounting = cashflow_summary(run_id, db_path, account=broker.account)
    accounting.update(accounting_broker.accounting_state())
    cashflows = load_cashflow_postings(run_id, db_path, account=broker.account)
    dataset = {s:[{**r,'timestamp':utc(r['timestamp']).isoformat()} for r in df.to_dict('records')] for s,df in bars.items()}
    return {'manifest':manifest, 'dataset':dataset, 'metrics':metrics, 'trades':trades, 'run_id':run_id,
            'pending_candidates':len(trader.pending), 'censored_positions':len(broker.open_positions),
            'accounting': accounting, 'accounting_posting_statuses': posting_statuses,
            'pending_accounting_events': len(pending_accounting), 'cashflows': cashflows}


def export_result(result, directory):
    path = Path(directory)
    if (path / 'manifest.json').exists():
        raise ValueError('Refusing to overwrite a saved result directory; choose a new output directory')
    path.mkdir(parents=True, exist_ok=True)
    (path/'bars.json').write_text(json.dumps(result['dataset'],sort_keys=True,separators=(',',':'))+'\n')
    (path/'bars.meta.json').write_text(json.dumps({'feed':result['manifest']['feed']})+'\n')
    for key in ('manifest','metrics','trades'):
        (path / (key+'.json')).write_text(json.dumps(result[key], indent=2, sort_keys=True, allow_nan=False)+'\n')
    (path / 'cashflows.json').write_text(json.dumps(result['cashflows'], indent=2, sort_keys=True, allow_nan=False)+'\n')
    (path / 'accounting.json').write_text(json.dumps(result['accounting'], indent=2, sort_keys=True, allow_nan=False)+'\n')
    (path/'report.txt').write_text(format_report(result['metrics'])+'\n\n'
        + f"Censored positions: {result['censored_positions']}; pending candidates: {result['pending_candidates']}\n"
        + f"Accounting version {result['accounting']['accounting_version']}: "
        + f"{result['accounting']['postings']} postings; unavailable inputs {result['accounting']['unavailable_count']}.\n"
        + 'Fill policy: next completed five-minute close. Costs are modeled, not measured spread.\n'
        + f"Feed: {result['manifest']['feed']}. Dataset: {result['manifest']['dataset_sha256']}\n")


def replay_historical_corrections(bars, variants, output_root, *, feed='fixture', gate=None,
                                  gate_name='baseline', evaluation_start=None, metadata=None):
    """Write labeled base/adverse fixed-trade accounting corrections to new directories.

    This helper deliberately does not call a provider or claim that historical action or
    borrow coverage is complete.  Each variant is a supplied offline scenario and gets a
    distinct run, ledger and output directory.
    """
    root = Path(output_root)
    results = {}
    for name, variant in sorted(variants.items()):
        target = root / name
        if (target / 'manifest.json').exists():
            raise ValueError(f'Refusing to overwrite saved correction result: {target}')
        target.mkdir(parents=True, exist_ok=True)
        result = run_portfolio(
            bars, str(target / 'run.db'), feed=feed, gate=gate, gate_name=gate_name,
            evaluation_start=evaluation_start, accounting_events=variant.get('accounting_events', ()),
            accounting_coverage=variant.get('accounting_coverage', ()),
            accounting_mode='fixed_trade_restatement',
            metadata={**(metadata or {}), 'accounting_mode': 'fixed_trade_restatement',
                      'historical_correction': True, 'accounting_variant': name,
                      'accounting_status': 'historical correction on already examined data; not validation'},
        )
        export_result(result, target)
        results[name] = result
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', help='JSON mapping symbols to OHLCV records')
    parser.add_argument('--output', default='research-output')
    parser.add_argument('--db', default=config.BACKTEST_DB_PATH)
    args = parser.parse_args()
    if args.dataset:
        bars = {s: pd.DataFrame(rows) for s, rows in json.loads(Path(args.dataset).read_text()).items()}
        meta = Path(args.dataset).with_suffix('.meta.json')
        feed = json.loads(meta.read_text())['feed'] if meta.exists() else 'saved:unknown provenance'
    else:
        bars = {s:get_bars(s, config.BACKTEST_BARS) for s in config.WATCHLIST}
        feed = active_source_name()
    result = run_portfolio(bars, args.db, feed, metadata={'command': ['backtest.py','--dataset', args.dataset, '--output',args.output]})
    export_result(result, args.output)
    print(format_report(result['metrics']))
    print(f"Artifacts: {args.output}; run: {result['run_id']}")


if __name__ == '__main__':
    main()
