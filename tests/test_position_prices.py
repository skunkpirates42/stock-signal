import pytest
from unittest.mock import Mock

import requests

from dashboard.prices import PositionPrices


def configure(monkeypatch, trades, is_open=False):
    monkeypatch.setenv('ALPACA_API_KEY', 'offline-key')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'offline-secret')
    prices = Mock()
    prices.json.return_value = {'trades': trades}
    clock = Mock()
    clock.json.return_value = {'is_open': is_open}
    get = Mock(side_effect=[prices, clock])
    monkeypatch.setattr('dashboard.prices.requests.get', get)
    return get


def test_batch_cached_and_timestamp_preserved(monkeypatch):
    get = configure(monkeypatch, {'SPY': {'p': 105, 't': '2026-01-02T15:00:00Z'},
                                  'QQQ': {'p': 200, 't': '2026-01-02T15:00:01Z'}})
    service = PositionPrices()
    result = service.get(['SPY', 'QQQ', 'SPY'])
    assert result['prices']['SPY'] == {'price': 105, 'timestamp': '2026-01-02T15:00:00+00:00'}
    assert service.get(['QQQ', 'SPY']) == result
    assert get.call_count == 1
    assert get.call_args_list[0].kwargs['params'] == {'symbols': 'QQQ,SPY', 'feed': 'iex'}
    assert all(call.kwargs['timeout'] == 3 for call in get.call_args_list)
    assert 'offline' not in str(result)


def test_missing_credentials_and_empty_symbols_do_not_call_network(monkeypatch):
    get = Mock(side_effect=AssertionError('network forbidden'))
    monkeypatch.setattr('dashboard.prices.requests.get', get)
    assert PositionPrices().get(['SPY'])['prices'] == {}
    monkeypatch.setenv('ALPACA_API_KEY', 'offline')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'offline')
    assert PositionPrices().get([])['prices'] == {}
    get.assert_not_called()


def test_missing_invalid_prices_are_unavailable(monkeypatch):
    configure(monkeypatch, {'A': {'p': float('nan'), 't': '2026-01-02T15:00:00Z'},
                           'B': {'p': -1, 't': '2026-01-02T15:00:00Z'},
                           'C': {'p': 100, 't': 'invalid'},
                           'D': {'p': 100, 't': '2099-01-01T00:00:00Z'}})
    assert PositionPrices().get(['A', 'B', 'C', 'D', 'MISSING'])['prices'] == {}


def test_failure_clears_old_prices_and_is_cached(monkeypatch):
    get = configure(monkeypatch, {'SPY': {'p': 105, 't': '2026-01-02T15:00:00Z'}})
    service = PositionPrices()
    assert service.get(['SPY'])['prices']
    service._expires = 0
    get.side_effect = requests.Timeout('sensitive error must never be returned')
    result = service.get(['SPY'])
    assert result['prices'] == {}
    assert 'sensitive' not in str(result)
    service.get(['SPY'])
    assert get.call_count == 2


def test_endpoint_only_marks_live_positions(monkeypatch, tmp_path):
    from dashboard.app import create_app
    monkeypatch.setattr('dashboard.app.load_open_positions', lambda path, source: (
        [{'ticker': 'SPY'}] if source == 'live' else (_ for _ in ()).throw(AssertionError(source))))
    get = configure(monkeypatch, {'SPY': {'p': 100, 't': '2026-01-02T15:00:00Z'}})
    app = create_app(str(tmp_path / 'journal.db'))
    response = app.test_client().get('/api/position-prices?symbols=OTHER&source=backtest')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert list(response.json['prices']) == ['SPY']
    assert get.call_args_list[0].kwargs['params']['symbols'] == 'SPY'


def test_alpaca_nanosecond_timestamps_on_python39(monkeypatch):
    configure(monkeypatch, {'SPY': {'p': 105, 't': '2026-01-02T15:00:17.135906123Z'}})
    result = PositionPrices().get(['SPY'])
    assert result['prices']['SPY']['timestamp'] == '2026-01-02T15:00:17.135906+00:00'


@pytest.mark.parametrize("is_open", [True, False, None])
def test_shared_market_status_without_positions(monkeypatch, tmp_path, is_open):
    from dashboard.app import create_app
    monkeypatch.setenv('ALPACA_API_KEY', 'offline')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'offline')
    response = Mock()
    response.json.return_value = {'is_open': is_open}
    get = Mock(return_value=response)
    monkeypatch.setattr('dashboard.prices.requests.get', get)
    app = create_app(str(tmp_path / 'empty.db'))
    client = app.test_client()
    first = client.get('/api/market-status')
    assert first.json['market_open'] is is_open
    assert first.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/market-status').json == first.json
    assert get.call_count == 1


def test_clock_failure_does_not_report_closed(monkeypatch):
    from dashboard.prices import MarketStatus
    monkeypatch.setenv('ALPACA_API_KEY', 'offline')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'offline')
    monkeypatch.setattr('dashboard.prices.requests.get', Mock(side_effect=requests.Timeout()))
    assert MarketStatus().get()['market_open'] is None
