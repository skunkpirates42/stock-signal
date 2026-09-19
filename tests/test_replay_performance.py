import json
from pathlib import Path

import pandas as pd
import pytest

from backtest import run_portfolio
from db.logger import _connect, init_db, replay_connection


def test_cached_and_uncached_replays_have_identical_results(tmp_path):
    source = json.loads((Path(__file__).parent / 'fixtures/bars.json').read_text())
    bars = {s: pd.DataFrame(rows) for s, rows in source.items()}
    uncached = run_portfolio(bars, str(tmp_path / 'uncached.db'))
    cache = {}
    first = run_portfolio(bars, str(tmp_path / 'first.db'), indicator_cache=cache)
    size = len(cache)
    second = run_portfolio(bars, str(tmp_path / 'second.db'), indicator_cache=cache)
    assert len(cache) == size and size > 0
    assert uncached['metrics'] == first['metrics'] == second['metrics']
    for file in ('uncached.db', 'first.db', 'second.db'):
        with _connect(str(tmp_path / file)) as conn:
            rows = [tuple(r) for r in conn.execute('SELECT ticker,bar_timestamp,direction,confidence,indicators_json,regime,skip_reason FROM signals ORDER BY id')]
        if file == 'uncached.db':
            expected = rows
        else:
            assert rows == expected


def test_replay_connection_rolls_back_failed_session_and_resets_scope(tmp_path):
    db = str(tmp_path / 'journal.db')
    init_db(db)
    with pytest.raises(RuntimeError):
        with replay_connection(db) as conn:
            with _connect(db) as inner:
                assert inner is conn
                inner.execute("INSERT INTO signals(ticker) VALUES ('committed')")
            conn.commit()
            with _connect(db) as inner:
                inner.execute("INSERT INTO signals(ticker) VALUES ('rolled_back')")
            raise RuntimeError('Interrupted replay')
    with _connect(db) as conn:
        assert [r['ticker'] for r in conn.execute('SELECT ticker FROM signals')] == ['committed']
        conn.execute("INSERT INTO signals(ticker) VALUES ('normal_connection')")
    with _connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM signals').fetchone()[0] == 2
