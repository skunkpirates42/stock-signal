"""Save explicit-date Alpaca IEX bars for offline research; never submits orders.

Run from the repository root: python -m data.download_history --help
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import config  # Loads the repo .env without overriding exported credentials.
from backtest import normalize_bars
from data.alpaca_rest import _client
from data.sessions import calendar, session_bounds, utc


def download(start, end, output, symbols=None, client=None):
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    start, end = utc(start), utc(end)
    if pd.isna(start) or pd.isna(end) or start >= end:
        raise ValueError('Start must precede the exclusive end')
    if end > utc(datetime.now(timezone.utc)) - pd.Timedelta(minutes=15):
        raise ValueError('End must be at least 15 minutes in the past')
    symbols = list(dict.fromkeys(symbols or config.WATCHLIST))
    if 'SPY' not in symbols or len(symbols) < 2:
        raise ValueError('Include SPY and at least one other symbol')
    output = Path(output)
    if output.exists():
        raise ValueError('Output directory already exists; choose a new directory to preserve datasets')
    if client is None:
        if not (os.getenv('ALPACA_API_KEY') and os.getenv('ALPACA_SECRET_KEY')):
            raise ValueError('Set ALPACA_API_KEY and ALPACA_SECRET_KEY in the repository .env file')
        client = _client()
        # Bound each SDK HTTP request; SDK still handles paging and rate-limit retries.
        request = client._session.request
        def timed_request(*args, **kwargs):
            kwargs.setdefault('timeout', (10, 60))
            return request(*args, **kwargs)
        client._session.request = timed_request
    expected = {}
    for year in range(start.year, end.year + 1):
        for day in calendar(year).sessions:
            label = str(day.date())
            opening, closing = session_bounds(label + 'T17:00Z')
            buckets = pd.date_range(opening, closing, freq='5min', inclusive='left')
            count = sum(start <= ts and ts + pd.Timedelta(minutes=5) <= end for ts in buckets)
            if count:
                expected[label] = count
    if not expected:
        raise ValueError('Interval contains no complete regular-session bars')
    dataset, coverage = {}, {}
    for symbol in symbols:
        # No total limit: alpaca-py follows next_page_token to exhaustion.
        response = client.get_stock_bars(StockBarsRequest(
            symbol_or_symbols=symbol, start=start.to_pydatetime(), end=end.to_pydatetime(),
            timeframe=TimeFrame(5, TimeFrameUnit.Minute), feed=DataFeed.IEX, adjustment=Adjustment.RAW))
        frame = response.df
        if frame is None or frame.empty:
            raise ValueError(f'No bars returned for {symbol}; no dataset published')
        frame = normalize_bars(frame.reset_index())
        frame = frame[(frame.timestamp >= start) &
                      (frame.timestamp + pd.Timedelta(minutes=5) <= end)].copy()
        if frame.empty:
            raise ValueError(f'No complete regular-session bars for {symbol}')
        if any((ts - session_bounds(ts)[0]) % pd.Timedelta(minutes=5) != pd.Timedelta(0) for ts in frame.timestamp):
            raise ValueError(f'Unaligned five-minute timestamps for {symbol}')
        counts = frame.groupby(frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')).size()
        coverage[symbol] = {
            'bars': len(frame), 'first_bar': frame.timestamp.min().isoformat(),
            'last_bar': frame.timestamp.max().isoformat(),
            'sessions': {day: {'observed': int(counts.get(day, 0)), 'expected': n,
                               'missing': n - int(counts.get(day, 0))} for day, n in sorted(expected.items())}}
        frame['timestamp'] = frame.timestamp.map(lambda ts: ts.isoformat())
        dataset[symbol] = frame.to_dict('records')
        print(f'{symbol}: {len(frame)} regular-session bars, {len(counts)} sessions', flush=True)
    serialized = json.dumps(dataset, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    metadata = {
        'provider': 'Alpaca', 'feed': 'alpaca:iex', 'adjustment': 'raw',
        'timeframe': '5Min', 'timestamp_semantics': 'UTC bar start',
        'session_filter': 'XNYS regular hours; complete bars only',
        'requested_start': start.isoformat(), 'requested_end_exclusive': end.isoformat(),
        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'symbols': symbols,
        'alpaca_py_version': version('alpaca-py'),
        'dataset_file_sha256': hashlib.sha256(serialized.encode()).hexdigest(),
        'coverage': coverage,
        'limitations': ['IEX is a single-exchange feed, not consolidated market volume.',
                       'Missing bars are not filled or converted to zero volume.',
                       'Raw prices are unadjusted; review corporate actions before replay.']}
    output.mkdir(parents=True)
    (output / 'bars.json').write_text(serialized)
    (output / 'bars.meta.json').write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n')
    # Completion marker is written last; incomplete directories must not be consumed.
    (output / 'COMPLETE').write_text(metadata['dataset_file_sha256'] + '\n')
    print(f'Saved {output / "bars.json"}', flush=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, help='Inclusive UTC timestamp or date')
    parser.add_argument('--end', required=True, help='Exclusive UTC timestamp or date')
    parser.add_argument('--output', required=True, help='New directory under research-output/')
    parser.add_argument('--symbols', nargs='+', default=config.WATCHLIST)
    args = parser.parse_args()
    try:
        download(args.start, args.end, args.output, args.symbols)
    except ValueError as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()
