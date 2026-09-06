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
from db.logger import init_db, start_run, _connect
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
    for _, group in df.groupby('timestamp'):
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
            'schema_version':1}


def run_portfolio(bars, db_path=None, feed='fixture', gate=None, gate_name='baseline', evaluation_start=None, metadata=None):
    db_path = db_path or config.BACKTEST_DB_PATH
    bars = {s: normalize_bars(df) for s, df in bars.items()}
    manifest = manifest_for(bars, feed, gate_name)
    manifest.update(metadata or {})
    manifest["evaluation_start"] = str(evaluation_start) if evaluation_start else None
    init_db(db_path)
    run_id = start_run(manifest, db_path)
    broker = PaperBroker()
    trader = LiveTrader(bars, db_path=db_path, source='backtest', broker=broker, run_id=run_id, gate=gate, evaluation_start=evaluation_start)
    events = {}
    for s, df in bars.items():
        for bar in df.to_dict('records'):
            events.setdefault(utc(bar['timestamp']), {})[s] = bar
    for ts in sorted(events):
        trader.process_batch(events[ts])
    with _connect(db_path) as conn:
        trades = [dict(r) for r in conn.execute('SELECT t.*, s.regime FROM trades t LEFT JOIN signals s ON s.id=t.signal_id '
                  'WHERE t.run_id=? ORDER BY t.exit_at IS NULL,t.exit_at,t.ticker,t.id', (run_id,))]
    metrics = compute_metrics(trades)
    metrics['equity'] = equity_curve(trades)
    dataset = {s:[{**r,'timestamp':utc(r['timestamp']).isoformat()} for r in df.to_dict('records')] for s,df in bars.items()}
    return {'manifest':manifest, 'dataset':dataset, 'metrics':metrics, 'trades':trades, 'run_id':run_id,
            'pending_candidates':len(trader.pending), 'censored_positions':len(broker.open_positions)}


def export_result(result, directory):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path/'bars.json').write_text(json.dumps(result['dataset'],sort_keys=True,separators=(',',':'))+'\n')
    (path/'bars.meta.json').write_text(json.dumps({'feed':result['manifest']['feed']})+'\n')
    for key in ('manifest','metrics','trades'):
        (path / (key+'.json')).write_text(json.dumps(result[key], indent=2, sort_keys=True, allow_nan=False)+'\n')
    (path/'report.txt').write_text(format_report(result['metrics'])+'\n\n'
        + f"Censored positions: {result['censored_positions']}; pending candidates: {result['pending_candidates']}\n"
        + 'Fill policy: next completed five-minute close. Costs are modeled, not measured spread.\n'
        + f"Feed: {result['manifest']['feed']}. Dataset: {result['manifest']['dataset_sha256']}\n")


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
