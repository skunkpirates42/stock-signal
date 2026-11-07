import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
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
        create_app(
            db_path=str(database_path),
            demo_db_path=str(sample_directory / "demo-artifacts.db"),
            demo_job_db_path=str(sample_directory / "demo-jobs.db"),
            demo_owner_id="smoke-test",
        ).run(host="127.0.0.1", port=18000, debug=False)


if __name__ == "__main__":
    main()
