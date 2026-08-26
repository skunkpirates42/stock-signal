"""argparse's `choices` only validates a value the user typed, not a default drawn from
config — so this covers the explicit post-parse check that catches an unsupported
LLM_PROVIDER (e.g. "template") slipping through as the --provider default.
"""

import pytest

import config
from db.logger import init_db
from scripts import backfill_reasoning


def test_unsupported_default_provider_exits_with_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    monkeypatch.setattr(
        "sys.argv", ["backfill_reasoning.py", "--db", str(tmp_path / "d.db")]
    )

    with pytest.raises(SystemExit) as exc_info:
        backfill_reasoning.main()

    assert exc_info.value.code == 2
    assert "anthropic" in capsys.readouterr().err


def test_explicit_provider_overrides_bad_default(monkeypatch, tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    monkeypatch.setattr(
        "sys.argv",
        ["backfill_reasoning.py", "--db", db, "--provider", "groq", "--dry-run"],
    )

    assert backfill_reasoning.main() == 0
