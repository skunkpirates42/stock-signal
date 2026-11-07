"""Dashboard entry point.

Starts the local web dashboard over papertrader.db.

Run:  python3 run_dashboard.py
Then open http://127.0.0.1:8000  (set DASHBOARD_PORT in .env to change the port).
"""

import logging

from flask import Flask, Response, request
from waitress import serve

import config
from app_logging import configure_logging
from dashboard.app import create_app


def keep_request_log_on_console(app: Flask) -> None:
    request_log = logging.getLogger("dashboard.requests")
    if not request_log.handlers:
        request_log.addHandler(logging.StreamHandler())
    request_log.setLevel(logging.INFO)
    request_log.propagate = False

    @app.after_request
    def log_response(response: Response) -> Response:
        request_log.info("%s %r %s", request.method, request.path, response.status_code)
        return response


def main() -> None:
    configure_logging("dashboard")
    app = create_app()
    keep_request_log_on_console(app)
    print(f"Dashboard at http://127.0.0.1:{config.DASHBOARD_PORT}  (Ctrl-C to stop)")
    serve(app, host="127.0.0.1", port=config.DASHBOARD_PORT)


if __name__ == "__main__":
    main()
