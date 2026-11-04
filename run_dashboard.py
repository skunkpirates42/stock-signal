"""Dashboard entry point.

Starts the local web dashboard over papertrader.db.

Run:  python3 run_dashboard.py
Then open http://127.0.0.1:8000  (set DASHBOARD_PORT in .env to change the port).
"""

import logging

import config
from app_logging import configure_logging
from dashboard.app import create_app


def keep_request_log_on_console() -> None:
    # Werkzeug only adds its own console handler when nothing on root handles INFO.
    # Keep its banner and per-request lines on the console (the launcher's api.log)
    # instead of the rotating event log.
    request_log = logging.getLogger("werkzeug")
    request_log.addHandler(logging.StreamHandler())
    request_log.setLevel(logging.INFO)
    request_log.propagate = False


def main() -> None:
    configure_logging("dashboard")
    keep_request_log_on_console()
    print(f"Dashboard at http://127.0.0.1:{config.DASHBOARD_PORT}  (Ctrl-C to stop)")
    create_app().run(host="127.0.0.1", port=config.DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
