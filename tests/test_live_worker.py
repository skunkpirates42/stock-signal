"""Worker failures remain visible until a subsequent batch succeeds."""
import logging

from db.logger import _connect
from live.trader import LiveTrader
from live.worker import TradingWorker


def bar(ts):
    return dict(timestamp=ts, open=100, high=101, low=99, close=100, volume=10)


def status(trader):
    with _connect(trader.db_path) as conn:
        return dict(conn.execute('SELECT * FROM runtime_status WHERE scope=?', (trader.scope,)).fetchone())


def fail_batch(trader, monkeypatch, ts='2026-06-10T14:00Z'):
    def fail(_):
        raise ValueError('forced batch failure')
    monkeypatch.setattr(trader, '_regime', fail)
    trader.ready[ts] = {'AAA': bar(ts)}
    worker = TradingWorker(trader)
    worker.on_minute_bar('UNKNOWN', '2026-06-10T14:00Z', 100, 101, 99, 100, 1)
    # Drain one event synchronously; tick consumes the ready batch and throws.
    worker.stopping = True
    worker._run()
    return worker


def test_worker_logs_original_exception_with_traceback(tmp_path, monkeypatch, caplog):
    trader = LiveTrader(['AAA'], str(tmp_path / 'worker.db'))
    with caplog.at_level(logging.ERROR):
        fail_batch(trader, monkeypatch)
    errors = [record for record in caplog.records if record.exc_info]
    assert errors
    assert errors[0].exc_info[0] is ValueError
    assert 'forced batch failure' in caplog.text
    assert 'Traceback' in caplog.text


def test_failure_survives_recovery_and_tick_until_new_batch(tmp_path, monkeypatch):
    trader = LiveTrader(['AAA'], str(tmp_path / 'worker.db'))
    fail_batch(trader, monkeypatch)
    trader.recover_worker_error()
    trader.tick('2026-06-10T14:06Z')
    row = status(trader)
    assert row['status'] == 'blocked'
    assert 'ValueError: forced batch failure' in row['detail']
    assert '1' in row['detail'] and 'not retried' in row['detail']
    assert trader.worker_failure_count == 1
    assert not trader.ready
    monkeypatch.setattr(trader, '_regime', lambda _: None)
    trader.process_batch({'AAA': bar('2026-06-10T14:00Z')})
    assert trader.worker_failure_count == 1  # already-consumed batch is not success
    trader.process_batch({'AAA': bar('2026-06-10T14:05Z')})
    assert trader.worker_failure_count == 0
    assert trader.worker_error is None
    trader.tick('2026-06-10T14:11Z')
    assert status(trader)['status'] == 'running'


def test_every_failure_is_logged_and_counted(tmp_path, monkeypatch, caplog):
    trader = LiveTrader(['AAA'], str(tmp_path / 'worker.db'))
    with caplog.at_level(logging.ERROR):
        fail_batch(trader, monkeypatch)
        fail_batch(trader, monkeypatch, '2026-06-10T14:05Z')
    assert len([record for record in caplog.records if record.exc_info]) == 2
    assert trader.worker_failure_count == 2
    assert 'consecutive worker failures: 2' in status(trader)['detail']


def test_original_exception_logged_even_if_failure_status_cannot_persist(tmp_path, monkeypatch, caplog):
    import live.worker as worker_module
    trader = LiveTrader(['AAA'], str(tmp_path / 'worker.db'))

    def unavailable(*args, **kwargs):
        raise RuntimeError('status storage unavailable')

    monkeypatch.setattr(worker_module, 'set_status', unavailable)
    with caplog.at_level(logging.ERROR):
        fail_batch(trader, monkeypatch)
    assert [record.exc_info[0] for record in caplog.records if record.exc_info] == [ValueError, RuntimeError]
    assert trader.worker_failure_count == 1
