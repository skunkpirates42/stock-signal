import logging
import re

import pytest

import config
from app_logging import configure_logging
from live.trader import LiveTrader
from tests.test_alpaca_broker import LONG, FakeClient, broker
from tests.test_correctness import bar, candidate

SECRET = "sentinel-secret-value-123"


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
    assert "to_state=filled" in events(caplog, "order_state")[0].getMessage()


def test_broker_error_is_a_warning_with_its_reason(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient()
    client.fail = "before"
    broker(tmp_path, client).open_position(LONG, 0)
    [record] = events(caplog, "order_unresolved")
    assert record.levelno == logging.WARNING
    assert 'error="TimeoutError: request uncertain"' in record.getMessage()


def test_reconcile_block_is_logged_once_with_reason_then_cleared(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient()
    b = broker(tmp_path, client)
    client.fail = "positions"
    b.reconcile()
    b.reconcile()
    [blocked] = events(caplog, "reconcile_blocked")
    assert blocked.levelno == logging.WARNING
    assert "positions unavailable" in blocked.getMessage()
    client.fail = None
    b.reconcile()
    [cleared] = events(caplog, "reconcile_clear")
    assert "safe_to_flatten=True" in cleared.getMessage()


def test_logged_events_carry_no_credentials(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("ALPACA_API_KEY", SECRET)
    monkeypatch.setenv("ALPACA_SECRET_KEY", SECRET)
    caplog.set_level(logging.DEBUG)
    client = FakeClient()
    b = broker(tmp_path, client)
    b.open_position(LONG, 0, 1)
    client.fail = "after"
    b.close_position("NVDA", 104, "WIN", 2)
    client.fail = "positions"
    b.reconcile()
    assert caplog.records
    assert SECRET not in caplog.text
