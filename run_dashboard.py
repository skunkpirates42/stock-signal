"""Dashboard entry point.

Starts the local web dashboard over papertrader.db.

Run:  python3 run_dashboard.py
Then open http://127.0.0.1:8000  (set DASHBOARD_PORT in .env to change the port).
"""

import config
from dashboard.app import create_app


def main() -> None:
    print(f"Dashboard at http://127.0.0.1:{config.DASHBOARD_PORT}  (Ctrl-C to stop)")
    create_app().run(host="127.0.0.1", port=config.DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
