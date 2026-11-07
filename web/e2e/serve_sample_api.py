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
