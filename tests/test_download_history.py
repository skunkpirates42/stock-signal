import hashlib
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from data.download_history import download


class FakeClient:
    def __init__(self):
        self.requests = []

    def get_stock_bars(self, request):
        self.requests.append(request)
        rows = [{'symbol': request.symbol_or_symbols, 'timestamp': pd.Timestamp(t),
                 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 150}
                for t in ('2026-06-10T13:25Z', '2026-06-10T13:30Z',
                          '2026-06-10T19:55Z', '2026-06-11T13:30Z')]
        return SimpleNamespace(df=pd.DataFrame(rows).set_index(['symbol', 'timestamp']))


def test_explicit_request_and_replay_ready_save(tmp_path):
    client = FakeClient()
    output = tmp_path / 'saved'
    metadata = download('2026-06-10', '2026-06-11', output, ['AAA', 'SPY'], client)
    for request in client.requests:
        assert request.feed.value == 'iex'
        assert request.adjustment.value == 'raw'
        assert request.timeframe.value == '5Min'
        assert request.limit is None
    saved = json.loads((output / 'bars.json').read_text())
    assert len(saved['AAA']) == 2  # premarket and exclusive end removed
    assert metadata['coverage']['AAA']['sessions']['2026-06-10'] == {'observed': 2, 'expected': 78, 'missing': 76}
    assert metadata['dataset_file_sha256'] == hashlib.sha256((output / 'bars.json').read_bytes()).hexdigest()
    assert (output / 'COMPLETE').read_text().strip() == metadata['dataset_file_sha256']
    with pytest.raises(ValueError, match='already exists'):
        download('2026-06-10', '2026-06-11', output, ['AAA', 'SPY'], client)
    assert len(client.requests) == 2


def test_missing_credentials_does_not_publish_dataset(tmp_path, monkeypatch):
    monkeypatch.delenv('ALPACA_API_KEY', raising=False)
    monkeypatch.delenv('ALPACA_SECRET_KEY', raising=False)
    with pytest.raises(ValueError, match='ALPACA_API_KEY'):
        download('2026-06-10', '2026-06-11', tmp_path / 'saved')
    assert not (tmp_path / 'saved').exists()


def test_missing_symbol_aborts_save(tmp_path):
    class EmptyClient:
        def get_stock_bars(self, request):
            return SimpleNamespace(df=pd.DataFrame())
    with pytest.raises(ValueError, match='No bars'):
        download('2026-06-10', '2026-06-11', tmp_path / 'saved', client=EmptyClient())
    assert not (tmp_path / 'saved').exists()
