"""Replay one claimed demo job inside a worker-owned attempt directory.

Run as ``python -E -s -m demo.replay_child <attempt_dir>``. The worker supplies the
environment; this process blocks broker, LLM and network clients before importing the
engine, re-validates the stored request, and writes only inside the attempt directory.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

EXIT_VALIDATION_FAILED = 3
EXIT_INPUT_UNAVAILABLE = 4
BLOCKED_MODULES = ("alpaca", "trades.alpaca_broker", "anthropic", "groq", "openai")


def _refuse_network(*args, **kwargs):
    raise OSError("Network access is disabled in the demo replay worker")


def isolate() -> None:
    # A None entry makes any later import of that module raise ImportError.
    for name in BLOCKED_MODULES:
        sys.modules[name] = None
    socket.socket.connect = _refuse_network
    socket.socket.connect_ex = _refuse_network
    socket.create_connection = _refuse_network
    socket.getaddrinfo = _refuse_network


def write_phase(attempt_dir: Path, phase: str) -> None:
    pending = attempt_dir / "phase.tmp"
    pending.write_text(phase)
    os.replace(pending, attempt_dir / "phase")


def replay(attempt_dir: Path) -> int:
    import config
    from backtest import export_result, run_portfolio
    from demo.replay_catalog import ReplayRequestRejected, build_replay_request, strategy_version_for

    job = json.loads((attempt_dir / "job.json").read_text())
    expected = job["normalized_run"]
    write_phase(attempt_dir, "validating")
    try:
        built = build_replay_request(job["request"])
    except ReplayRequestRejected as exc:
        print("Replay request rejected: %s" % exc.code, file=sys.stderr)
        return EXIT_INPUT_UNAVAILABLE if exc.code == "dataset_unavailable" else EXIT_VALIDATION_FAILED
    profile = built.cost_profile
    checks = {
        "broker": config.BROKER == "local",
        "cost_profile": (config.SPREAD_BPS, config.SLIPPAGE_BPS, config.FEE_PER_SHARE) == (
            profile.spread_bps, profile.slippage_bps_per_fill, profile.fee_per_share_per_fill),
        "selected_data": built.normalized_run["selected_data_sha256"] == expected["selected_data_sha256"],
        "strategy_version": (built.normalized_run["strategy_version"] == expected["strategy_version"]
                             and strategy_version_for(job["strategy_configuration"])
                             == expected["strategy_version"]["value"]),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        print("Replay no longer matches the queued run: %s" % ", ".join(failed), file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    write_phase(attempt_dir, "replaying")
    result = run_portfolio(built.bars, str(attempt_dir / "run.db"), feed=expected["feed"]["value"],
                           evaluation_start=built.evaluation_start)
    write_phase(attempt_dir, "exporting")
    export_result(result, attempt_dir / "output")
    (attempt_dir / "engine-run.json").write_text(json.dumps({"engine_run_id": result["run_id"]}))
    return 0


def main(argv) -> int:
    isolate()
    return replay(Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
