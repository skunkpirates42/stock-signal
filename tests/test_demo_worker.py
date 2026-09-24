import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import demo.worker as worker_module
from demo.jobs import FAILURE_SUMMARIES, JobStore, LeaseLost
from demo.replay_catalog import COST_PROFILES, build_replay_request
from demo.replay_child import EXIT_VALIDATION_FAILED
from demo.worker import DemoWorker

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("engine_demo_contract", ROOT / "docs/engine-demo/validate.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
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


def test_isolated_child_does_not_load_credentials_from_a_dotenv_file(tmp_path):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("ALPACA_API_KEY=sentinel-secret-0123456789\n")
    script = ("import os, dotenv; from demo.replay_child import isolate; isolate(); import config; "
              "dotenv.load_dotenv(%r); from dotenv import load_dotenv; load_dotenv(%r); "
              "print('ALPACA_API_KEY' in os.environ)" % (str(dotenv_file), str(dotenv_file)))
    completed = subprocess.run([sys.executable, "-E", "-s", "-c", script], cwd=str(ROOT),
                               env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
    assert completed.stdout.strip() == "False", completed.stderr


def test_child_refuses_to_replay_while_holding_a_credential(tmp_path):
    attempt_dir = tmp_path / "attempt"
    write_attempt(attempt_dir)
    completed = run_child(attempt_dir, child_env(ALPACA_API_KEY="sentinel-secret-0123456789"))
    assert completed.returncode == EXIT_VALIDATION_FAILED
    assert "ALPACA_API_KEY" in completed.stderr and "sentinel-secret" not in completed.stderr
    assert not (attempt_dir / "run.db").exists()


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


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.db")


@pytest.fixture
def worker(store, tmp_path):
    return DemoWorker(store, tmp_path / "worker", lease_seconds=5, heartbeat_seconds=0.1, timeout_seconds=60)


def fake_child(monkeypatch, tmp_path, body):
    script = tmp_path / "fake_child.py"
    script.write_text("import json, os, sys, time\nfrom pathlib import Path\nattempt = Path(sys.argv[1])\n" + body)
    monkeypatch.setattr(worker_module, "CHILD_COMMAND", (sys.executable, str(script)))


def wait_for(condition, seconds=10):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def run_in_background(worker):
    outcome = {}
    thread = threading.Thread(target=lambda: outcome.setdefault("value", worker.run_once()))
    thread.start()
    return thread, outcome


def process_is_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_fixture_job_completes_offline_and_publishes_only_verified_files(store, worker, tmp_path):
    job_id, _ = store.submit("local", run_request())
    assert worker.run_once() == "completed"
    data = store.job_detail("local", job_id)["data"]
    status, result, artifacts = data["status"], data["result"], data["artifacts"]
    contract.validate([contract.envelope(data["run"]), contract.envelope(status), contract.envelope(result)]
                      + [contract.envelope(artifact) for artifact in artifacts])
    assert (status["state"], status["result_id"]["value"]) == ("completed", result["id"])
    assert status["engine_run_id"]["availability"] == "available"
    assert result["metrics"]["recorded_costs"]["observation"]["value"] > 0
    names = {artifact["kind"] for artifact in artifacts}
    assert names == {"manifest", "metrics", "trades", "accounting", "cashflows", "report", "dataset_metadata"}
    published = tmp_path / "worker" / "results" / result["id"]
    for artifact in artifacts:
        content = store.artifact_content("local", job_id, artifact["id"]).content
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    assert not (published / "bars.json").exists()
    assert json.loads((published / "manifest.json").read_text())["settings"]["SPREAD_BPS"] == 2.0
    assert sorted(path.name for path in (tmp_path / "worker" / "results").iterdir()) == [result["id"]]
    assert list((tmp_path / "worker" / "attempts").iterdir()) == []
    assert (tmp_path / "worker" / "logs" / job_id / "attempt-1.log").is_file()
    assert worker.run_once() is None


def test_child_main_blocks_broker_llm_and_network_before_replaying(tmp_path):
    sentinel = tmp_path / "sentinel.json"
    script = (
        "import json, socket, sys\n"
        "import demo.replay_child as child\n"
        "def probe(attempt_dir):\n"
        "    reached = []\n"
        "    for module in ('trades.alpaca_broker', 'alpaca', 'anthropic', 'groq'):\n"
        "        try:\n"
        "            __import__(module)\n"
        "            reached.append(module)\n"
        "        except ImportError:\n"
        "            pass\n"
        "    try:\n"
        "        socket.create_connection(('127.0.0.1', 9))\n"
        "        reached.append('network')\n"
        "    except OSError as exc:\n"
        "        if 'disabled' not in str(exc):\n"
        "            reached.append('network')\n"
        "    open(%r, 'w').write(json.dumps(reached))\n"
        "    return 0\n"
        "child.replay = probe\n"
        "sys.exit(child.main(['replay_child', %r]))\n" % (str(sentinel), str(tmp_path)))
    completed = subprocess.run([sys.executable, "-E", "-s", "-c", script], cwd=str(ROOT),
                               env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(sentinel.read_text()) == []


def test_worker_starts_the_child_without_python_environment_or_user_site():
    assert worker_module.CHILD_COMMAND == (sys.executable, "-E", "-s", "-m", "demo.replay_child")


def test_hostile_parent_environment_does_not_reach_the_replay(store, worker, tmp_path, monkeypatch):
    secret = "sentinel-secret-0123456789"
    for name, value in (("PYTHONPATH", str(tmp_path)), ("BROKER", "alpaca"), ("LLM_PROVIDER", "anthropic"),
                        ("ALPACA_API_KEY", secret), ("ALPACA_SECRET_KEY", secret), ("ANTHROPIC_API_KEY", secret),
                        ("DB_PATH", str(tmp_path / "journal.db")), ("BACKTEST_DB_PATH", str(tmp_path / "backtest.db"))):
        monkeypatch.setenv(name, value)
    job_id, _ = store.submit("local", run_request())
    assert worker.run_once() == "completed"
    assert not (tmp_path / "journal.db").exists() and not (tmp_path / "backtest.db").exists()
    log = (tmp_path / "worker" / "logs" / job_id / "attempt-1.log").read_text()
    assert secret not in log


def test_child_environment_carries_no_credentials(store, worker, tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_SECRET_KEY", "sentinel-secret-0123456789")
    monkeypatch.setenv("SESSION_POLICY", "overnight")
    dump = tmp_path / "child-env.json"
    fake_child(monkeypatch, tmp_path, "Path(%r).write_text(json.dumps(dict(os.environ)))\nsys.exit(1)\n" % str(dump))
    store.submit("local", run_request(cost_profile_id="adverse-v2"))
    assert worker.run_once() == "failed"
    environment = json.loads(dump.read_text())
    assert not {"ALPACA_SECRET_KEY", "PYTHONPATH", "HOME"} & set(environment)
    assert (environment["BROKER"], environment["LLM_PROVIDER"], environment["SPREAD_BPS"]) == ("local", "template", "5.0")
    assert environment["SESSION_POLICY"] == "overnight"


def test_cancel_stops_a_running_child(store, worker, tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    fake_child(monkeypatch, tmp_path, "Path(%r).write_text(str(os.getpid()))\ntime.sleep(60)\n" % str(pid_file))
    job_id, _ = store.submit("local", run_request())
    thread, outcome = run_in_background(worker)
    wait_for(pid_file.exists)
    store.request_cancel("local", job_id)
    thread.join(timeout=15)
    assert outcome["value"] == "cancelled"
    assert store.job_detail("local", job_id)["data"]["status"]["state"] == "cancelled"
    assert process_is_gone(int(pid_file.read_text()))


def test_timeout_stops_the_child_and_fails_the_job(store, tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    fake_child(monkeypatch, tmp_path, "Path(%r).write_text(str(os.getpid()))\ntime.sleep(60)\n" % str(pid_file))
    job_id, _ = store.submit("local", run_request())
    worker = DemoWorker(store, tmp_path / "worker", lease_seconds=5, heartbeat_seconds=0.1, timeout_seconds=0.5)
    assert worker.run_once() == "failed"
    assert store.job_detail("local", job_id)["data"]["status"]["failure"]["code"] == "timeout"
    assert process_is_gone(int(pid_file.read_text()))


@pytest.mark.parametrize("exit_code, failure_code", [
    (3, "validation_failed"), (4, "input_unavailable"), (1, "execution_failed")])
def test_child_exit_codes_map_to_fixed_failures(store, worker, tmp_path, monkeypatch, exit_code, failure_code):
    fake_child(monkeypatch, tmp_path, "sys.exit(%d)\n" % exit_code)
    job_id, _ = store.submit("local", run_request())
    assert worker.run_once() == "failed"
    failure = store.job_detail("local", job_id)["data"]["status"]["failure"]
    assert (failure["code"], failure["summary"]) == (failure_code, FAILURE_SUMMARIES[failure_code])


@pytest.mark.parametrize("removed", ["trades.json", "metrics.json"])
def test_partial_output_is_never_published(store, worker, tmp_path, monkeypatch, removed):
    fake_child(monkeypatch, tmp_path, (
        "import subprocess\n"
        "subprocess.run([sys.executable, '-E', '-s', '-m', 'demo.replay_child', str(attempt)], check=True)\n"
        "(attempt / 'output' / %r).unlink()\n" % removed))
    job_id, _ = store.submit("local", run_request())
    assert worker.run_once() == "failed"
    data = store.job_detail("local", job_id)["data"]
    assert (data["status"]["failure"]["code"], data["result"], data["artifacts"]) == ("artifact_invalid", None, [])
    assert list((tmp_path / "worker" / "results").iterdir()) == []


def test_lost_lease_stops_the_child_without_publishing(store, worker, tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    fake_child(monkeypatch, tmp_path, "Path(%r).write_text(str(os.getpid()))\ntime.sleep(60)\n" % str(pid_file))
    job_id, _ = store.submit("local", run_request())
    thread, outcome = run_in_background(worker)
    wait_for(pid_file.exists)
    with sqlite3.connect(str(tmp_path / "jobs.db")) as conn:
        conn.execute("UPDATE demo_jobs SET lease_expires_at=0 WHERE id=?", (job_id,))
    assert store.recover_expired_leases() == {job_id: "queued"}
    thread.join(timeout=15)
    assert outcome["value"] == "lease_lost"
    assert process_is_gone(int(pid_file.read_text()))
    assert store.job_detail("local", job_id)["data"]["status"]["state"] == "queued"
    assert list((tmp_path / "worker" / "results").iterdir()) == []


def test_result_published_after_recovery_took_the_job_is_removed(store, worker, tmp_path, monkeypatch):
    job_id, _ = store.submit("local", run_request())

    def recovered_first(*args, **kwargs):
        raise LeaseLost("recovered")

    monkeypatch.setattr(store, "complete", recovered_first)
    assert worker.run_once() == "lease_lost"
    assert list((tmp_path / "worker" / "results").iterdir()) == []
    assert store.job_detail("local", job_id)["data"]["result"] is None


def test_kept_log_is_sanitized(store, worker, tmp_path, monkeypatch):
    secret = "sentinel-secret-0123456789"
    monkeypatch.setenv("ALPACA_SECRET_KEY", secret)
    fake_child(monkeypatch, tmp_path, "print(attempt, %r, %r, %r)\nsys.exit(1)\n" % (
        str(ROOT / "backtest.py"), secret, str(Path.home() / "notes")))
    job_id, _ = store.submit("local", run_request())
    assert worker.run_once() == "failed"
    log_path = tmp_path / "worker" / "logs" / job_id / "attempt-1.log"
    log = log_path.read_text()
    assert "<attempt> <repo>/backtest.py [redacted] ~/notes" in log
    assert secret not in log and str(tmp_path) not in log
    assert log_path.stat().st_mode & 0o077 == 0


def test_heartbeat_must_be_shorter_than_the_lease(store, tmp_path):
    with pytest.raises(ValueError):
        DemoWorker(store, tmp_path / "worker", lease_seconds=5, heartbeat_seconds=5)
