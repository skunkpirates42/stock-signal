import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from demo.replay_catalog import COST_PROFILES, build_replay_request
from demo.replay_child import EXIT_VALIDATION_FAILED

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ID = "6f1d0a52-3c1b-4f7e-9a51-0c6a1f4e2b10"


def run_request(**overrides):
    return {"strategy_id": "stock-signal", "dataset_id": FIXTURE_ID, "window_id": "fixture-day-2",
            "cost_profile_id": "base-v2", "idempotency_key": "click-0001", **overrides}


def child_env(**overrides):
    return {"PATH": os.environ["PATH"], "BROKER": "local", "LLM_PROVIDER": "template",
            **COST_PROFILES["base-v2"].child_environment(), **overrides}


def write_attempt(attempt_dir, **run_overrides):
    built = build_replay_request(run_request())
    attempt_dir.mkdir()
    (attempt_dir / "job.json").write_text(json.dumps({
        "request": run_request(), "normalized_run": {**built.normalized_run, **run_overrides},
        "strategy_configuration": built.strategy_configuration}))


def run_child(attempt_dir, env):
    return subprocess.run([sys.executable, "-E", "-s", "-m", "demo.replay_child", str(attempt_dir)],
                          cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("statement", [
    "import trades.alpaca_broker", "import alpaca", "import anthropic",
    "import socket; socket.create_connection(('127.0.0.1', 9))",
    "import socket; socket.socket().connect(('127.0.0.1', 9))",
])
def test_isolated_child_cannot_reach_a_broker_llm_or_network(statement):
    script = "from demo.replay_child import isolate; isolate(); " + statement
    completed = subprocess.run([sys.executable, "-c", script], cwd=str(ROOT), capture_output=True, text=True)
    assert completed.returncode != 0
    assert "halted; None in sys.modules" in completed.stderr or "Network access is disabled" in completed.stderr


@pytest.mark.parametrize("env_overrides, run_overrides", [
    ({"SPREAD_BPS": "0"}, {}),
    ({"BROKER": "alpaca"}, {}),
    ({}, {"selected_data_sha256": {"availability": "available", "value": "0" * 64, "reason": None,
                                   "detail": None}}),
])
def test_child_refuses_a_replay_that_no_longer_matches_the_queued_run(tmp_path, env_overrides, run_overrides):
    attempt_dir = tmp_path / "attempt"
    write_attempt(attempt_dir, **run_overrides)
    completed = run_child(attempt_dir, child_env(**env_overrides))
    assert completed.returncode == EXIT_VALIDATION_FAILED
    assert not (attempt_dir / "output").exists() and not (attempt_dir / "run.db").exists()
