import json
import os
import runpy
import sqlite3
import subprocess
import sys
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
        app.run(host="127.0.0.1", port=18000, debug=False)


if __name__ == "__main__":
    main()
