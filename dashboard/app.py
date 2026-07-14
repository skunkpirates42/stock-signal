"""Local web dashboard.

A lightweight Flask app that reads the existing papertrader.db and serves a single
auto-refreshing page: performance stat cards, a realized-equity curve, per-ticker
breakdown, open positions, and recent trades/signals. Reuses analytics.metrics so the
numbers match report.py exactly.

Run:  python3 run_dashboard.py   (then open http://127.0.0.1:8000)
"""

import sqlite3

from flask import Flask, jsonify, render_template

import config
from alerts.feed import build_alert_events
from analytics.metrics import compute_metrics, equity_curve, load_closed_trades
from db.logger import load_open_positions


def create_app(db_path: str = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or config.DB_PATH

    def _db():
        return app.config["DB_PATH"]

    def _recent(table: str, limit: int = 50):
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except sqlite3.OperationalError:
            return []  # table not created yet
        finally:
            conn.close()
        return [dict(r) for r in rows]

    @app.route("/")
    def index():
        return render_template("index.html", port=config.DASHBOARD_PORT)

    @app.route("/api/metrics")
    def api_metrics():
        trades = load_closed_trades(_db())
        m = compute_metrics(trades)
        m["equity"] = equity_curve(trades)
        return jsonify(m)

    @app.route("/api/trades")
    def api_trades():
        return jsonify(_recent("trades", 100))

    @app.route("/api/signals")
    def api_signals():
        return jsonify(_recent("signals", 100))

    @app.route("/api/open")
    def api_open():
        return jsonify(load_open_positions(_db()))

    @app.route("/api/alerts")
    def api_alerts():
        # Unified, newest-first stream of alert-worthy events (actionable signals + trade
        # opens/closes). Filtering is done client-side so the UI controls stay responsive.
        events = build_alert_events(_recent("signals", 200), _recent("trades", 200), limit=80)
        return jsonify(events)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=config.DASHBOARD_PORT, debug=False)
