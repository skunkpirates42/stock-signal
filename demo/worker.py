"""One local worker that runs claimed demo jobs in a bounded, isolated subprocess.

Each attempt gets a private directory. The child replays there; nothing is public until
the worker has verified the output, renamed it into the results directory and recorded
it with the job's completion. One host and one worker only, like the job store.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from dotenv import dotenv_values

from .artifacts import RUN_ARTIFACTS, ArtifactIndex
from .availability import available, unavailable
from .jobs import PHASES, ClaimedJob, JobStore, LeaseLost, PublishedArtifact, PublishedResult
from .replay_catalog import COST_PROFILES, ROOT
from .replay_child import CREDENTIAL_NAME_WORDS, EXIT_INPUT_UNAVAILABLE, EXIT_VALIDATION_FAILED

CHILD_COMMAND = (sys.executable, "-E", "-s", "-m", "demo.replay_child")
# These shape the strategy fingerprint, so the child must see the server's values to
# rebuild the same strategy_version. Credentials and everything else stay behind.
PASSED_ENVIRONMENT = ("PATH", "LANG", "SESSION_POLICY", "BAR_LATENESS_SECONDS", "ACCOUNT_NAMESPACE")
PUBLISHED_FILES = ("manifest.json", "metrics.json", "trades.json", "accounting.json", "cashflows.json",
                   "report.txt", "bars.meta.json")
CHILD_FAILURES = {EXIT_VALIDATION_FAILED: "validation_failed", EXIT_INPUT_UNAVAILABLE: "input_unavailable"}
DOTENV_PATH = ROOT / ".env"
MAX_LOG_BYTES = 64 * 1024
# Extra bytes read beyond the kept size, so dropping the partial first line still leaves a full log.
REDACTION_MARGIN_BYTES = 4 * 1024
STOP_GRACE_SECONDS = 5
POLL_SECONDS = 2


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _signal_group(child: subprocess.Popen, signal_number: int) -> None:
    try:
        os.killpg(child.pid, signal_number)
    except (ProcessLookupError, PermissionError):
        # macOS answers EPERM while the group's exited leader is not yet reaped.
        pass


def _stop(child: subprocess.Popen) -> None:
    # Signal the group even after the child exits: processes it started are still in it.
    _signal_group(child, signal.SIGTERM)
    try:
        child.wait(timeout=STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    _signal_group(child, signal.SIGKILL)
    child.wait()


def _fsync_directory(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _credential_values() -> List[str]:
    sources = [os.environ, dotenv_values(DOTENV_PATH) if DOTENV_PATH.is_file() else {}]
    values = {value for source in sources for name, value in source.items()
              if value and len(value) >= 8 and any(word in name.upper() for word in CREDENTIAL_NAME_WORDS)}
    return sorted(values, key=len, reverse=True)


def sanitize_log(text: str, attempt_dir: Path) -> str:
    for value in _credential_values():
        text = text.replace(value, "[redacted]")
    for path, label in ((str(attempt_dir), "<attempt>"), (str(ROOT), "<repo>"), (str(Path.home()), "~")):
        text = text.replace(path, label)
    return text


def result_record(result_id: str, run: Dict[str, Any], metrics: Dict[str, Any],
                  artifact_ids: List[str]) -> Dict[str, Any]:
    realized_basis = "Realized closed trades; " + metrics["metric_basis"]

    def measured(source_name: str, unit: str, basis: str = realized_basis) -> Dict[str, Any]:
        return {"observation": available(metrics[source_name]), "unit": unit, "basis": basis,
                "source_pointer": "/metrics/" + source_name}

    def missing(unit: str, reason: str, basis: str, detail: str) -> Dict[str, Any]:
        return {"observation": unavailable(reason, detail), "unit": unit, "basis": basis, "source_pointer": None}

    no_marked = ("No marked valuation is produced by a demo job replay.",
                 "The job replay does not produce a marked review.")
    no_amount = "No separate accounting amount; no zero imputation."
    values = {
        "realized_net_pnl": measured("total_pnl", "USD"),
        "gross_pnl": measured("gross_pnl", "USD"),
        "recorded_costs": measured("costs", "USD"),
        "closed_trades": measured("n_closed", "count"),
        "censored_positions": measured("n_open", "count", "Positions open at window end; not realized closes."),
        "realized_max_drawdown": measured("max_drawdown", "USD"),
        "marked_net_pnl": missing("USD", "not_recorded", *no_marked),
        "marked_max_drawdown": missing("USD", "not_recorded", *no_marked),
        "marked_net_per_session": missing("USD/session", "not_recorded", *no_marked),
        "max_gross_exposure": missing("USD", "not_recorded", *no_marked),
        "borrow_cost": missing("USD", "not_modeled", no_amount, "Short borrow is not modeled by the replay."),
        "dividend_cashflow": missing("USD", "not_modeled", no_amount, "Dividend cash flows are not modeled by the replay."),
        "spread_cost": missing("USD", "not_recorded", no_amount, "Recorded costs are an aggregate; spread is not separated."),
        "slippage_cost": missing("USD", "not_recorded", no_amount, "Recorded costs are an aggregate; slippage is not separated."),
        "fees": missing("USD", "not_recorded", no_amount, "Recorded costs are an aggregate; fees are not separated."),
    }
    by_regime = (available({"basis": realized_basis, "unit": "USD", "source_pointer": "/metrics/by_regime",
                            "values": metrics["by_regime"]})
                 if "by_regime" in metrics else unavailable("not_recorded", "The replay recorded no regime breakdown."))
    evidence = ("Synthetic correctness fixture; no strategy evidence." if run["provenance"]["synthetic"]
                else "Retrospective replay of already examined market data; not a validation.")
    return {"record_type": "result", "id": result_id, "run_id": run["id"], "window": run["window"],
            "variant": run["variant"], "provenance": run["provenance"], "accounting": run["accounting"],
            "metrics": values, "by_regime": by_regime,
            "limitations": ["Accounting incomplete: borrow and dividend cash flows are unresolved.",
                            "Costs are modeled scenario rates, not measured spread or fills.", evidence],
            "artifact_ids": artifact_ids}


class DemoWorker:
    def __init__(self, store: JobStore, root: Path | str, *, lease_seconds: float = 30.0,
                 heartbeat_seconds: float = 5.0, timeout_seconds: float = 900.0):
        if not 0 < heartbeat_seconds < lease_seconds:
            raise ValueError("heartbeat_seconds must be positive and shorter than lease_seconds")
        if not timeout_seconds > 0:
            raise ValueError("timeout_seconds must be positive")
        self.store = store
        root = Path(root).resolve()
        self.attempts_dir, self.logs_dir, self.results_dir = root / "attempts", root / "logs", root / "results"
        for directory in (self.attempts_dir, self.logs_dir, self.results_dir):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.timeout_seconds = timeout_seconds

    def run_once(self) -> Optional[str]:
        self.store.recover_expired_leases()
        job = self.store.claim_next(lease_seconds=self.lease_seconds)
        if job is None:
            return None
        attempt_dir = self.attempts_dir / job.lease_token
        attempt_dir.mkdir(mode=0o700)
        try:
            (attempt_dir / "job.json").write_text(json.dumps({
                "request": job.request, "normalized_run": job.normalized_run,
                "strategy_configuration": job.strategy_configuration}))
            return self._supervise(job, attempt_dir)
        except LeaseLost:
            return "lease_lost"
        finally:
            self._keep_sanitized_log(job, attempt_dir)
            shutil.rmtree(attempt_dir, ignore_errors=True)

    def _child_environment(self, job: ClaimedJob, attempt_dir: Path) -> Dict[str, str]:
        environment = {name: os.environ[name] for name in PASSED_ENVIRONMENT if name in os.environ}
        environment.update(COST_PROFILES[job.request["cost_profile_id"]].child_environment())
        environment.update(BROKER="local", LLM_PROVIDER="template",
                           DB_PATH=str(attempt_dir / "journal.db"), BACKTEST_DB_PATH=str(attempt_dir / "run.db"))
        return environment

    @staticmethod
    def _phase(attempt_dir: Path) -> Optional[str]:
        try:
            phase = (attempt_dir / "phase").read_text()
        except OSError:
            return None
        return phase if phase in PHASES else None

    def _supervise(self, job: ClaimedJob, attempt_dir: Path) -> str:
        with open(attempt_dir / "child.log", "wb") as log:
            child = subprocess.Popen([*CHILD_COMMAND, str(attempt_dir)], cwd=str(ROOT),
                                     env=self._child_environment(job, attempt_dir), stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                try:
                    returncode = child.wait(timeout=min(self.heartbeat_seconds,
                                                        max(0.0, deadline - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    pass
                if time.monotonic() >= deadline:
                    _stop(child)
                    self.store.fail(job.id, job.lease_token, code="timeout")
                    return "failed"
                state = self.store.heartbeat(job.id, job.lease_token, lease_seconds=self.lease_seconds,
                                             phase=self._phase(attempt_dir))
                if state == "cancel_requested":
                    _stop(child)
                    self.store.confirm_cancelled(job.id, job.lease_token)
                    return "cancelled"
        finally:
            _stop(child)
        if returncode != 0:
            self.store.fail(job.id, job.lease_token, code=CHILD_FAILURES.get(returncode, "execution_failed"))
            return "failed"
        state = self.store.heartbeat(job.id, job.lease_token, lease_seconds=self.lease_seconds, phase="verifying")
        if state == "cancel_requested":
            self.store.confirm_cancelled(job.id, job.lease_token)
            return "cancelled"
        try:
            engine_run_id, record, artifacts, contents = self._verified_output(job, attempt_dir)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            with open(attempt_dir / "child.log", "a") as log:
                log.write("Output verification failed: %s\n" % exc)
            self.store.fail(job.id, job.lease_token, code="artifact_invalid")
            return "failed"
        try:
            published = self._publish(record["id"], contents)
        except OSError as exc:
            with open(attempt_dir / "child.log", "a") as log:
                log.write("Publishing failed: %s\n" % exc)
            self.store.fail(job.id, job.lease_token, code="execution_failed")
            return "failed"
        try:
            self.store.complete(job.id, job.lease_token, engine_run_id=engine_run_id,
                                result=PublishedResult(record["id"], str(published), record, artifacts))
        except LeaseLost:
            # Recovery took the job, so this directory will never be referenced.
            shutil.rmtree(published, ignore_errors=True)
            raise
        return "completed"

    def _verified_output(self, job: ClaimedJob, attempt_dir: Path) -> Tuple[
            str, Dict[str, Any], Tuple[PublishedArtifact, ...], Dict[str, bytes]]:
        output = attempt_dir / "output"
        engine_run_id = json.loads((attempt_dir / "engine-run.json").read_text())["engine_run_id"]
        contents = {}
        for name in PUBLISHED_FILES:
            path = output / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Replay output is missing " + name)
            contents[name] = path.read_bytes()
        manifest = json.loads(contents["manifest.json"])
        metrics = json.loads(contents["metrics.json"])
        run, policy = job.normalized_run, job.normalized_run["cost_policy"]
        settings = manifest["settings"]
        if (manifest["dataset_sha256"] != run["selected_data_sha256"]["value"]
                or manifest["feed"] != run["feed"]["value"]
                or (manifest["source"], manifest["backend"]) != ("backtest", "local")
                or (settings["SPREAD_BPS"], settings["SLIPPAGE_BPS"], settings["FEE_PER_SHARE"]) != (
                    policy["spread_bps"], policy["slippage_bps_per_fill"], policy["fee_per_share_per_fill"])):
            raise ValueError("Replay output does not match the queued run")
        result_id = str(uuid.uuid4())
        artifacts = tuple(PublishedArtifact(str(uuid.uuid4()), RUN_ARTIFACTS[name][0], name, _sha256(content),
                                            RUN_ARTIFACTS[name][1], len(content))
                          for name, content in sorted(contents.items()))
        record = result_record(result_id, run, metrics, [artifact.id for artifact in artifacts])
        contract = ArtifactIndex._contract_module()
        try:
            contract.validate([contract.envelope(record)]
                              + [contract.envelope(artifact.as_record(result_id)) for artifact in artifacts])
        except Exception as exc:
            raise ValueError("Result record fails the A1 schema") from exc
        return engine_run_id, record, artifacts, contents

    def _publish(self, result_id: str, contents: Dict[str, bytes]) -> Path:
        staging = self.results_dir / (".staging-" + result_id)
        published = self.results_dir / result_id
        staging.mkdir(mode=0o700)
        try:
            for name, content in contents.items():
                with open(staging / name, "xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            _fsync_directory(staging)
            os.rename(str(staging), str(published))
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        _fsync_directory(self.results_dir)
        return published

    def _keep_sanitized_log(self, job: ClaimedJob, attempt_dir: Path) -> None:
        try:
            with open(attempt_dir / "child.log", "rb") as handle:
                handle.seek(0, os.SEEK_END)
                truncated = handle.tell() > MAX_LOG_BYTES
                read_start = max(0, handle.tell() - MAX_LOG_BYTES - REDACTION_MARGIN_BYTES)
                handle.seek(read_start)
                raw = handle.read()
        except OSError:
            return
        if read_start > 0:
            # A secret cut by the read start can only sit on this partial line, where redaction can't match it.
            newline = raw.find(b"\n")
            raw = raw[newline + 1:] if newline >= 0 else b""
        kept = sanitize_log(raw.decode("utf-8", "replace"), attempt_dir).encode("utf-8")
        if truncated:
            kept = b"[earlier output truncated]\n" + kept[-MAX_LOG_BYTES:].decode("utf-8", "ignore").encode("utf-8")
        job_logs = self.logs_dir / job.id
        job_logs.mkdir(exist_ok=True, mode=0o700)
        fd = os.open(str(job_logs / ("attempt-%d.log" % job.attempt)), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as log:
            log.write(kept)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run queued local demo jobs one at a time.")
    parser.add_argument("--job-db", default=os.environ.get("DEMO_JOB_DB_PATH")
                        or str(Path(config.DB_PATH).with_name("demo-jobs.db")))
    parser.add_argument("--root", help="Attempts, logs and results directory (default: demo-worker next to the job DB)")
    parser.add_argument("--timeout", type=float, default=900.0, help="Seconds before a replay is stopped")
    parser.add_argument("--once", action="store_true", help="Run at most one job, then exit")
    args = parser.parse_args(argv)
    worker = DemoWorker(JobStore(args.job_db), args.root or Path(args.job_db).with_name("demo-worker"),
                        timeout_seconds=args.timeout)
    # Exit through Python so the supervising finally block stops a running child.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        outcome = worker.run_once()
        if args.once:
            return 0
        if outcome is None:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
