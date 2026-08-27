"""poc.py writes signals tagged source="poc", never "live" — it runs on synthetic data
whenever Alpaca credentials are absent, and log_signal defaults source to "live".
"""

import sqlite3

import config
import poc


def test_main_logs_signals_with_poc_source(tmp_path, monkeypatch):
    db = str(tmp_path / "poc.db")
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    poc.main()

    conn = sqlite3.connect(db)
    sources = {row[0] for row in conn.execute("SELECT DISTINCT source FROM signals")}
    conn.close()

    assert sources == {"poc"}
