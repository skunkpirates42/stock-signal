"""Local web dashboard.

A lightweight Flask app that reads the existing papertrader.db and serves a single
auto-refreshing page: performance stat cards, a realized-equity curve, per-ticker
breakdown, open positions, and recent trades/signals. Reuses analytics.metrics so the
numbers match report.py exactly.

Run:  python3 run_dashboard.py   (then open http://127.0.0.1:8000)
"""

import os
import sqlite3
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request

import config
from alerts.feed import build_alert_events
from analytics.metrics import compute_metrics, equity_curve, load_closed_trades
from db.logger import load_open_positions, init_db, scope_sql, _connect
from demo.jobs import IdempotencyConflict, JobStore
from demo.read_service import MAX_JSON_RESPONSE_BYTES, DemoContentTooLarge, DemoNotFound, DemoReadService
from demo.replay_catalog import ReplayRequestRejected
from signals.llm_synthesis import signal_from_row, synthesize


MAX_RUN_REQUEST_BYTES = 4096


def create_app(db_path: str = None, *, demo_db_path: str = None, demo_owner_id: str = None,
               demo_job_db_path: str = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or config.DB_PATH
    # These are server configuration, never request parameters.  The demo index is
    # deliberately separate from the operational journal and has no write endpoint.
    app.config["DEMO_DB_PATH"] = (demo_db_path or os.environ.get("DEMO_ARTIFACT_DB_PATH")
                                  or str(Path(app.config["DB_PATH"]).with_name("demo-artifacts.db")))
    app.config["DEMO_OWNER_ID"] = demo_owner_id or os.environ.get("DEMO_OPERATOR_OWNER_ID", "local")
    app.config["DEMO_JOB_DB_PATH"] = (demo_job_db_path or os.environ.get("DEMO_JOB_DB_PATH")
                                      or str(Path(app.config["DB_PATH"]).with_name("demo-jobs.db")))
    init_db(app.config["DB_PATH"])
    demo = DemoReadService(app.config["DEMO_DB_PATH"], owner_id=app.config["DEMO_OWNER_ID"])
    jobs = JobStore(app.config["DEMO_JOB_DB_PATH"])

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

    def _demo_json(operation):
        try:
            payload = operation()
            # Flask owns JSON configuration (including Unicode escaping), so cap the
            # actual serialized response rather than an approximation of it.
            response = jsonify(payload)
            if len(response.get_data()) > MAX_JSON_RESPONSE_BYTES:
                raise DemoContentTooLarge("Demo JSON response exceeds the configured response limit")
            return response
        except DemoNotFound:
            # Keep absent, wrong-owner, malformed IDs, and unavailable/tampered indexed
            # sources indistinguishable to the caller.
            abort(404)
        except DemoContentTooLarge:
            abort(413, "demo content exceeds the configured response limit")
        except ValueError as exc:
            abort(400, str(exc))

    @app.route("/api/demo/v1/strategies")
    def api_demo_strategies():
        return _demo_json(demo.strategy_catalog)

    @app.route("/api/demo/v1/datasets")
    def api_demo_datasets():
        return _demo_json(lambda: demo.dataset_catalog(limit=request.args.get("limit")))

    @app.route("/api/demo/v1/cost-profiles")
    def api_demo_cost_profiles():
        return _demo_json(lambda: demo.cost_profile_catalog(limit=request.args.get("limit")))

    @app.route("/api/demo/v1/research")
    def api_demo_research():
        return _demo_json(lambda: demo.list_research(limit=request.args.get("limit"),
                                                      cursor=request.args.get("cursor")))

    @app.route("/api/demo/v1/results/<result_id>")
    def api_demo_result(result_id):
        return _demo_json(lambda: demo.result_detail(result_id))

    @app.route("/api/demo/v1/results/<result_id>/artifacts/<artifact_id>")
    def api_demo_artifact(result_id, artifact_id):
        try:
            artifact = demo.artifact_content(result_id, artifact_id)
        except DemoNotFound:
            abort(404)
        except DemoContentTooLarge:
            abort(413, "demo content exceeds the configured response limit")
        response = Response(artifact.content, mimetype=artifact.mime_type)
        response.headers["Content-Length"] = str(artifact.byte_size)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def _demo_error(status: int, code: str, message: str) -> Response:
        response = jsonify({"error": {"code": code, "message": message}})
        response.status_code = status
        return response

    def _is_lock_timeout(exc: sqlite3.OperationalError) -> bool:
        # Python 3.9 has no sqlite_errorcode; SQLITE_BUSY/LOCKED are only visible in the message.
        message = str(exc)
        return "locked" in message or "busy" in message

    def _demo_run_json(operation):
        try:
            return jsonify(operation())
        except DemoNotFound:
            return _demo_error(404, "not_found", "No run with this ID in this scope.")
        except ValueError as exc:
            return _demo_error(400, "invalid_request", str(exc))
        except sqlite3.OperationalError as exc:
            if not _is_lock_timeout(exc):
                raise
            return _demo_error(503, "job_store_busy", "The job store is busy; try again.")

    @app.route("/api/demo/v1/runs", methods=["POST"])
    def api_demo_submit_run():
        # Requiring a JSON body makes a cross-site form post fail CORS preflight.
        if not request.is_json:
            return _demo_error(415, "unsupported_media_type", "Run requests must be application/json.")
        if request.content_length is None or request.content_length > MAX_RUN_REQUEST_BYTES:
            return _demo_error(413, "request_too_large", "Run requests must declare a small JSON body.")
        body = request.get_json(silent=True)
        if body is None:
            return _demo_error(400, "invalid_request", "Run request body is not valid JSON.")
        try:
            job_id, _ = jobs.submit(app.config["DEMO_OWNER_ID"], body)
        except ReplayRequestRejected as exc:
            return _demo_error(400, exc.code, str(exc))
        except IdempotencyConflict as exc:
            return _demo_error(409, "idempotency_conflict", str(exc))
        except sqlite3.OperationalError as exc:
            if not _is_lock_timeout(exc):
                raise
            return _demo_error(503, "job_store_busy", "The job store is busy; try again.")
        response = _demo_run_json(lambda: jobs.job_detail(app.config["DEMO_OWNER_ID"], job_id))
        if response.status_code == 200:
            response.status_code = 202
            response.headers["Location"] = "/api/demo/v1/runs/" + job_id
        return response

    @app.route("/api/demo/v1/runs")
    def api_demo_runs():
        return _demo_run_json(lambda: jobs.list_jobs(app.config["DEMO_OWNER_ID"], limit=request.args.get("limit"),
                                                     cursor=request.args.get("cursor")))

    @app.route("/api/demo/v1/runs/<run_id>")
    def api_demo_run(run_id):
        return _demo_run_json(lambda: jobs.job_detail(app.config["DEMO_OWNER_ID"], run_id))

    @app.route("/api/demo/v1/runs/<run_id>/cancel", methods=["POST"])
    def api_demo_cancel_run(run_id):
        if not request.is_json:
            return _demo_error(415, "unsupported_media_type", "Cancel requests must be application/json.")
        return _demo_run_json(lambda: jobs.request_cancel(app.config["DEMO_OWNER_ID"], run_id))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=config.DASHBOARD_PORT, debug=False)
