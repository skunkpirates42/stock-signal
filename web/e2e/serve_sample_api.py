import json
import os
import runpy
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def seed_signal_search(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        rows = [
            ("DEEP", "SHORT", 0.95, "2026-06-10T23:59:59.999999Z", "live"),
            ("DEEP", "WAIT", 0.2, "2026-06-10T00:00:00Z", "live"),
            ("REPLAY_ONLY", "LONG", 0.9, "2026-06-10T12:00:00Z", "backtest"),
            *[("PAGE", "LONG", 0.8, "2026-07-15T12:00:00Z", "live")] * 551,
        ]
        connection.executemany(
            """INSERT INTO signals (ticker, direction, confidence, bar_timestamp,
               created_at, source) VALUES (?, ?, ?, ?, '2026-08-01T12:00:00Z', ?)""",
            rows,
        )


LARGE_FIXTURE_TRADES = 5_000


def seed_large_live_history(database_path: Path) -> None:
    tickers = ["AAA", "QQQ", "SPY", "MSFT", "NVDA", "AMD", "TSLA", "META"]
    regimes = ["TRENDING", "CHOPPY"]
    first_close = datetime(2025, 6, 2, 14, 0, tzinfo=timezone.utc)
    with sqlite3.connect(database_path) as connection:
        template = connection.execute(
            "SELECT indicators_json, reasoning FROM signals ORDER BY id LIMIT 1"
        ).fetchone()
        for index in range(LARGE_FIXTURE_TRADES):
            ticker = tickers[index % len(tickers)]
            direction = "LONG" if index % 3 else "SHORT"
            closed_at = first_close + timedelta(minutes=37 * index)
            opened_at = closed_at - timedelta(minutes=35)
            outcome = ("WIN", "LOSS", "LOSS", "WIN", "BREAKEVEN")[index % 5]
            pnl = {"WIN": 60.0 + index % 40, "LOSS": -35.0 - index % 25, "BREAKEVEN": 0.0}[outcome]
            signal_id = connection.execute(
                """INSERT INTO signals (ticker, bar_timestamp, direction, confidence, entry, stop,
                   target, rr, indicators_json, reasoning, regime, source, synthesis_source,
                   created_at, backend, account)
                   VALUES (?, ?, ?, 0.67, 100, 99, 102, 2.0, ?, ?, ?, 'live', 'template', ?,
                   'local', 'local')""",
                (
                    ticker,
                    opened_at.isoformat(),
                    direction,
                    template[0],
                    template[1],
                    regimes[index % 2],
                    opened_at.isoformat(),
                ),
            ).lastrowid
            connection.execute(
                """INSERT INTO trades (signal_id, ticker, direction, entry, stop, target, shares,
                   exit_price, outcome, pnl, bars_held, created_at, closed_at, source, backend,
                   account, entry_at, exit_at, gross_pnl, costs, exit_reason, remaining_shares)
                   VALUES (?, ?, ?, 100, 99, 102, 50, 101, ?, ?, 7, ?, ?, 'live', 'local',
                   'local', ?, ?, ?, 0, 'target', 0)""",
                (
                    signal_id,
                    ticker,
                    direction,
                    outcome,
                    pnl,
                    opened_at.isoformat(),
                    closed_at.isoformat(),
                    opened_at.isoformat(),
                    closed_at.isoformat(),
                    pnl,
                ),
            )


def seed_saved_research(sample_directory: Path) -> None:
    from demo.artifacts import ArtifactIndex

    fixture = json.loads(
        (REPOSITORY_ROOT / "docs/engine-demo/fixtures/synthetic-source.json").read_text()
    )
    source = sample_directory / "synthetic-result"
    digest = "a" * 64
    protocol = dict(fixture["protocol"], synthetic=True, dataset_file_sha256=digest)
    protocol["dataset_metadata"] = dict(protocol["dataset_metadata"], dataset_file_sha256=digest)
    row = fixture["comparison"][0]
    manifest = dict(
        fixture["manifest"],
        window=row["window"],
        gate=row["variant"],
        input_dataset_sha256=digest,
        dataset_metadata={"dataset_file_sha256": digest},
        settings={"SPREAD_BPS": 2.0, "SLIPPAGE_BPS": 1.0, "FEE_PER_SHARE": 0.0},
    )
    artifacts = {
        "protocol.json": protocol,
        "comparison.json": [row],
        "fixture/baseline/manifest.json": manifest,
        "fixture/baseline/metrics.json": row["metrics"],
        "fixture/baseline/diagnostics.json": row["diagnostics"],
    }
    for name, value in artifacts.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))
    ArtifactIndex(sample_directory / "demo-artifacts.db").import_directory(
        source, owner_id="smoke-test", synthetic=True
    )


def main() -> None:
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    runpy.run_path(str(REPOSITORY_ROOT / "tests/conftest.py"))
    sys.path.insert(0, str(REPOSITORY_ROOT))

    from dashboard.app import create_app

    with TemporaryDirectory(prefix="stock-signal-smoke-") as directory:
        sample_directory = Path(directory)
        database_path = sample_directory / "fixture.db"
        subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "backtest.py"),
                "--dataset",
                str(REPOSITORY_ROOT / "tests/fixtures/bars.json"),
                "--db",
                str(database_path),
                "--output",
                str(sample_directory / "report"),
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        seed_saved_research(sample_directory)
        app = create_app(
            db_path=str(database_path),
            demo_db_path=str(sample_directory / "demo-artifacts.db"),
            demo_job_db_path=str(sample_directory / "demo-jobs.db"),
            demo_owner_id="smoke-test",
        )
        seed_signal_search(database_path)
        if os.environ.get("PERF_FIXTURE") == "large":
            seed_large_live_history(database_path)
        app.run(host="127.0.0.1", port=18000, debug=False)


if __name__ == "__main__":
    main()
