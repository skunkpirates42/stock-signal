import logging
from unittest.mock import Mock

import pytest
from flask import Flask

import run_dashboard


@pytest.fixture
def request_logger(monkeypatch):
    logger = logging.getLogger("dashboard.requests")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    monkeypatch.setattr(logger, "propagate", True)
    return logger


def test_waitress_serves_configured_loopback_port(monkeypatch, tmp_path, request_logger, capsys):
    monkeypatch.setattr(run_dashboard.config, "DB_PATH", str(tmp_path / "dashboard.db"))
    monkeypatch.setattr(run_dashboard.config, "DASHBOARD_PORT", 8345)
    monkeypatch.setattr(run_dashboard, "configure_logging", Mock())
    server = Mock()
    monkeypatch.setattr(run_dashboard, "serve", server)

    run_dashboard.main()

    app = server.call_args.args[0]
    assert server.call_args.kwargs == {"host": "127.0.0.1", "port": 8345}
    assert app.test_client().get("/api/status").status_code == 200
    assert "GET '/api/status' 200" in capsys.readouterr().err


def test_request_log_stays_on_console_without_query_or_headers(request_logger, capsys, caplog):
    app = Flask(__name__)
    run_dashboard.keep_request_log_on_console(app)
    app.test_client().get(
        "/missing?token=private-query", headers={"Authorization": "private-header"}
    )

    console = capsys.readouterr().err
    assert "GET '/missing' 404" in console
    assert "private-query" not in console
    assert "private-header" not in console
    assert not caplog.records
