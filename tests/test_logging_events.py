import logging
import re

import pytest

import config
from app_logging import configure_logging
from data.sessions import utc
from live.trader import LiveTrader
from tests.test_alpaca_broker import LONG, FakeClient, broker
from tests.test_correctness import bar, candidate

MARKET_OPEN = utc("2026-06-10T15:00Z")


@pytest.fixture
def isolated_root_logger():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers, root.level = saved_handlers, saved_level


def events(caplog, name):
    return [r for r in caplog.records if r.getMessage().split(" ", 1)[0] == name]


def test_local_live_session_traces_one_signal_through_the_log_file(
    tmp_path, monkeypatch, isolated_root_logger
):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    monkeypatch.setattr(
        "live.trader.compute_indicators", lambda df: {"close": float(df.close.iloc[-1])}
    )
    monkeypatch.setattr("live.trader.generate_signal", candidate)
    configure_logging("live", log_dir=tmp_path / "logs")
    trader = LiveTrader(["AAA"], str(tmp_path / "live.db"))
    trader.process_batch({"AAA": bar("2026-06-10T14:00Z")})
    trader.process_batch({"AAA": bar("2026-06-10T14:05Z", 101)})
    trader.process_batch({"AAA": bar("2026-06-10T14:10Z", 105)})

    text = (tmp_path / "logs" / "live.log").read_text()
    signal_id = re.search(r" signal .*signal_id=(\d+)", text).group(1)
    traced = [
        line.split()[4] for line in text.splitlines() if f"signal_id={signal_id} " in line + " "
    ]
    assert traced == ["signal", "entry_pending", "position_opened", "position_closed"]
    closed = next(line for line in text.splitlines() if "position_closed" in line)
    assert "outcome=WIN" in closed and "exit_reason=target" in closed


def test_alpaca_order_events_share_one_order_id(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    broker(tmp_path, FakeClient()).open_position(LONG, 0, 7)
    intent = events(caplog, "order_intent")[0].getMessage()
    order_id = re.search(r"order_id=(\S+)", intent).group(1)
    assert "signal_id=7" in intent
    for name in ("order_submitted", "order_state"):
        assert f"order_id={order_id}" in events(caplog, name)[0].getMessage()
    order_state = events(caplog, "order_state")[0].getMessage()
    assert "state=filled" in order_state and "unresolved" not in order_state


def test_broker_error_is_a_warning_with_its_reason(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient()
    client.fail = "before"
    broker(tmp_path, client).open_position(LONG, 0)
    [record] = events(caplog, "order_unresolved")
    assert record.levelno == logging.WARNING
    assert 'error="TimeoutError: request uncertain"' in record.getMessage()


def alpaca_trader(tmp_path, client):
    return LiveTrader(["NVDA"], str(tmp_path / "orders.db"), broker=broker(tmp_path, client))


def test_reconcile_outage_logs_one_block_despite_changing_error_text(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient()
    trader = alpaca_trader(tmp_path, client)
    attempts = iter(range(100))

    def unreachable():
        raise ConnectionError(f"connection object at 0x{next(attempts):x} refused")

    client.get_all_positions = unreachable
    trader.tick(MARKET_OPEN)
    trader.tick(MARKET_OPEN)
    [blocked] = events(caplog, "execution_blocked")
    assert blocked.levelno == logging.WARNING
    assert "Reconciliation unavailable" in blocked.getMessage()
    del client.get_all_positions
    trader.tick(MARKET_OPEN)
    [running] = events(caplog, "execution_running")
    assert "safe_to_flatten=True" in running.getMessage()


def test_block_restored_by_trader_after_reconcile_is_logged_as_blocked(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    trader = alpaca_trader(tmp_path, FakeClient())
    trader.legacy_blocked = "Legacy open positions have unknown execution scope"
    trader.tick(MARKET_OPEN)
    [blocked] = events(caplog, "execution_blocked")
    assert "Legacy open positions" in blocked.getMessage()
    assert not events(caplog, "execution_running")


def test_local_entry_dropped_while_blocked_is_logged_with_its_signal(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    monkeypatch.setattr(
        "live.trader.compute_indicators", lambda df: {"close": float(df.close.iloc[-1])}
    )
    monkeypatch.setattr("live.trader.generate_signal", candidate)
    trader = LiveTrader(["AAA"], str(tmp_path / "live.db"))
    trader.process_batch({"AAA": bar("2026-06-10T14:00Z")})
    signal_id = re.search(r"signal_id=(\d+)", events(caplog, "entry_pending")[0].getMessage())[1]
    trader.broker.blocked = "operator hold"
    trader.process_batch({"AAA": bar("2026-06-10T14:05Z", 101)})
    [dropped] = events(caplog, "entry_dropped")
    assert f"signal_id={signal_id} " in dropped.getMessage()
    assert 'blocked="operator hold"' in dropped.getMessage()
    assert not events(caplog, "position_opened")


def test_alpaca_entry_too_small_for_one_share_is_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient()
    assert broker(tmp_path, client).open_position({**LONG, "entry": 1e9}, 0, 7) is None
    [skipped] = events(caplog, "order_skipped")
    assert (
        "signal_id=7" in skipped.getMessage() and "reason=under_one_share" in skipped.getMessage()
    )
    assert not client.submitted
