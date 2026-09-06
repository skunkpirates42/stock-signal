"""Local web dashboard.

A lightweight Flask app that reads the existing papertrader.db and serves a single
auto-refreshing page: performance stat cards, a realized-equity curve, per-ticker
breakdown, open positions, and recent trades/signals. Reuses analytics.metrics so the
numbers match report.py exactly.

Run:  python3 run_dashboard.py   (then open http://127.0.0.1:8000)
"""

import sqlite3

from flask import Flask, abort, jsonify, render_template, request

import config
from alerts.feed import build_alert_events
from analytics.metrics import compute_metrics, equity_curve, load_closed_trades
from db.logger import load_open_positions, init_db, scope_sql, _connect
from signals.llm_synthesis import signal_from_row, synthesize


def create_app(db_path: str = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or config.DB_PATH
    init_db(app.config["DB_PATH"])

    def _db():
        return app.config["DB_PATH"]

    def _recent(table: str, limit: int = 50, source: str = None):
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM %s" % table
        params = []
        clauses, params = scope_sql(source)
        if table in ("trades", "signals"):
            more, values = scope_sql(backend=request.args.get("backend"), account=request.args.get("account"))
            clauses += more
            params += values
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def _query_params(default_limit: int):
        raw = request.args.get("limit")
        if raw is None:
            return default_limit, request.args.get("source")
        try:
            limit = int(raw)
            if limit < 1 or limit > 5000:
                abort(400, "limit must be between 1 and 5000")
            return limit, request.args.get("source")
        except ValueError:
            abort(400, "limit must be an integer")

    @app.route("/")
    def index():
        return render_template("index.html", port=config.DASHBOARD_PORT)

    @app.route("/api/metrics")
    def api_metrics():
        trades = load_closed_trades(_db(), source=request.args.get("source"),
            backend=request.args.get("backend"), account=request.args.get("account"))
        m = compute_metrics(trades)
        m["equity"] = equity_curve(trades)
        return jsonify(m)

    @app.route("/api/trades")
    def api_trades():
        limit, source = _query_params(100)
        return jsonify(_recent("trades", limit, source))

    @app.route("/api/signals")
    def api_signals():
        limit, source = _query_params(100)
        return jsonify(_recent("signals", limit, source))

    @app.route("/api/open")
    def api_open():
        return jsonify(load_open_positions(_db(), source=request.args.get("source", "live"),
            backend=request.args.get("backend"), account=request.args.get("account")))

    @app.route("/api/signals/<int:signal_id>/explain", methods=["POST"])
    def api_explain(signal_id):
        # The live loop stores free template text for every signal; a real LLM call happens
        # only here, when someone actually asks to read one. Already-synthesized rows are
        # returned as-is so a second request costs nothing.
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM signals WHERE id = ?", (signal_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        if row is None:
            abort(404, "no signal %d" % signal_id)

        existing = row["synthesis_source"] or ""
        if existing and not existing.startswith("template"):
            return jsonify({"id": signal_id, "reasoning": row["reasoning"],
                            "synthesis_source": existing, "cached": True})

        result = synthesize(signal_from_row(row))
        source = result["synthesis_source"]
        # A fallback means the provider failed and the text is just the template the row
        # already has. Don't persist that — leave the row retryable on the next request.
        if not source.startswith("template"):
            conn = sqlite3.connect(_db())
            conn.execute(
                "UPDATE signals SET reasoning = ?, synthesis_source = ? WHERE id = ?",
                (result["reasoning"], source, signal_id),
            )
            conn.commit()
            conn.close()

        return jsonify({"id": signal_id, "reasoning": result["reasoning"],
                        "synthesis_source": source, "cached": False})

    @app.route("/api/alerts")
    def api_alerts():
        # Unified, newest-first stream of alert-worthy events (actionable signals + trade
        # opens/closes). Filtering is done client-side so the UI controls stay responsive.
        events = build_alert_events(_recent("signals", 200, request.args.get("source", "live")),
                                    _recent("trades", 200, request.args.get("source", "live")), limit=80)
        return jsonify(events)

    @app.route("/api/status")
    def api_status():
        with _connect(_db()) as conn:
            runtime = [dict(r) for r in conn.execute("SELECT * FROM runtime_status WHERE scope LIKE 'live:%'")]
            orders = [dict(r) for r in conn.execute("SELECT id,ticker,purpose,state,requested_qty,filled_qty,last_error,account "
                "FROM orders WHERE state NOT IN ('filled','canceled','rejected','expired','done_for_day','suspended')")]
            latest = conn.execute("SELECT MAX(bar_timestamp) FROM signals WHERE source='live'").fetchone()[0]
        return jsonify(runtime=runtime, unresolved_orders=orders, latest_bar=latest)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=config.DASHBOARD_PORT, debug=False)
