import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_smoke_api_clears_inherited_credentials_before_startup():
    environment = os.environ.copy()
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        environment[name] = "smoke-test-dummy-credential"
    environment["BROKER"] = "alpaca"
    environment["LLM_PROVIDER"] = "anthropic"
    startup_check = """
import os
import runpy
from unittest.mock import patch


def assert_offline_environment(*args, **kwargs):
    import config

    assert config.BROKER == "local"
    assert config.LLM_PROVIDER == "template"
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        assert os.environ.get(name) == "", f"{name} was not cleared"


with patch("subprocess.run", side_effect=assert_offline_environment) as replay:
    with patch("flask.Flask.run", side_effect=assert_offline_environment) as server:
        runpy.run_path("web/e2e/serve_sample_api.py", run_name="__main__")
    server.assert_called_once()
replay.assert_called_once()
"""
    result = subprocess.run(
        [sys.executable, "-c", startup_check],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
