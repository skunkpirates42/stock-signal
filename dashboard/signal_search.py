"""Read-only, paginated search over the complete operational signal journal."""

import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Mapping

from db.logger import scope_sql


@dataclass(frozen=True)
class SignalSearch:
    source: str
    ticker: str | None
    direction: str | None
    min_confidence: float
    start_date: str | None
    end_date: str | None
    include_wait: bool
    page: int
    page_size: int
    snapshot_id: int | None

    @classmethod
    def from_params(cls, params: Mapping[str, str]):
        source = params.get("source", "live")
        if source not in {"live", "all", "backtest", "poc", "unknown"}:
            raise ValueError("source must be live, all, backtest, poc or unknown")
        direction = params.get("direction") or None
        if direction not in {None, "LONG", "SHORT", "WAIT"}:
            raise ValueError("direction must be LONG, SHORT or WAIT")
        include_wait = params.get("include_wait", "false")
        if include_wait not in {"true", "false"}:
            raise ValueError("include_wait must be true or false")
        try:
            confidence = float(params.get("min_confidence", "0"))
        except ValueError:
            raise ValueError("min_confidence must be between 0 and 1") from None
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        start_date = _date_param(params, "from")
        end_date = _date_param(params, "to")
        if start_date and end_date and start_date > end_date:
            raise ValueError("from must be on or before to")
        ticker = params.get("ticker", "").strip().upper() or None
        if ticker and len(ticker) > 32:
            raise ValueError("ticker must be at most 32 characters")
        return cls(
            source=source,
            ticker=ticker,
            direction=direction,
            min_confidence=confidence,
            start_date=start_date,
            end_date=end_date,
            include_wait=include_wait == "true",
            page=_integer_param(params, "page", 1, 1, 2_147_483_647),
            page_size=_integer_param(params, "page_size", 50, 1, 100),
            snapshot_id=(
                _integer_param(params, "snapshot_id", 0, 0, 9_007_199_254_740_991)
                if "snapshot_id" in params
                else None
            ),
        )


def _integer_param(params, name, default, minimum, maximum):
    raw = params.get(name, str(default))
    if not re.fullmatch(r"[0-9]+", raw):
        raise ValueError(f"{name} must be an integer")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _date_param(params, name):
    raw = params.get(name)
    if not raw:
        return None
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise ValueError
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(f"{name} must be a YYYY-MM-DD date") from None


def _filter_clauses(search):
    clauses, values = scope_sql(search.source, prefix="s.")
    if search.ticker:
        clauses.append("s.ticker = ?")
        values.append(search.ticker)
    if search.direction:
        clauses.append("s.direction = ?")
        values.append(search.direction)
    clauses.append("s.confidence >= ?")
    values.append(search.min_confidence)
    timestamp = "signal_utc_day(COALESCE(s.bar_timestamp, s.created_at))"
    if search.start_date:
        clauses.append(f"{timestamp} >= ?")
        values.append(search.start_date)
    if search.end_date:
        clauses.append(f"{timestamp} <= ?")
        values.append(search.end_date)
    return clauses, values


def _utc_signal_day(timestamp):
    if not isinstance(timestamp, str):
        return None
    try:
        instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(timezone.utc).date().isoformat()
    except (ValueError, OverflowError):
        return None


def search_signals(db_path: str, search: SignalSearch) -> dict:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.create_function("signal_utc_day", 1, _utc_signal_day, deterministic=True)
    try:
        connection.execute("BEGIN")
        snapshot_id = search.snapshot_id
        if snapshot_id is None:
            snapshot_id = connection.execute("SELECT COALESCE(MAX(id), 0) FROM signals").fetchone()[
                0
            ]
        scope_clauses, scope_values = scope_sql(search.source, prefix="s.")
        scope_clauses.append("s.id <= ?")
        scope_values.append(snapshot_id)
        scope_where = " AND ".join(scope_clauses)
        scope_total = connection.execute(
            f"SELECT COUNT(*) FROM signals s WHERE {scope_where}", scope_values
        ).fetchone()[0]
        tickers = [
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT s.ticker FROM signals s WHERE {scope_where} ORDER BY s.ticker",
                scope_values,
            )
        ]
        clauses, values = _filter_clauses(search)
        clauses.append("s.id <= ?")
        values.append(snapshot_id)
        hidden_wait_count = 0
        if not search.include_wait and not search.direction:
            hidden_wait_count = connection.execute(
                "SELECT COUNT(*) FROM signals s WHERE "
                + " AND ".join(clauses)
                + " AND s.direction = 'WAIT'",
                values,
            ).fetchone()[0]
            clauses.append("s.direction != 'WAIT'")
        where = " AND ".join(clauses)
        total = connection.execute(
            f"SELECT COUNT(*) FROM signals s WHERE {where}", values
        ).fetchone()[0]
        total_pages = max(1, (total + search.page_size - 1) // search.page_size)
        page = min(search.page, total_pages)
        # A signal may have multiple trades; show the newest within its exact provenance.
        rows = connection.execute(
            f"""SELECT s.*, (
                SELECT t.outcome FROM trades t
                WHERE t.signal_id = s.id AND t.source IS s.source
                  AND t.backend IS s.backend AND t.account IS s.account
                ORDER BY t.id DESC LIMIT 1
            ) AS outcome
            FROM signals s WHERE {where}
            ORDER BY s.id DESC LIMIT ? OFFSET ?""",
            [*values, search.page_size, (page - 1) * search.page_size],
        ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "scope_total": scope_total,
            "hidden_wait_count": hidden_wait_count,
            "tickers": tickers,
            "page": page,
            "page_size": search.page_size,
            "total_pages": total_pages,
            "snapshot_id": snapshot_id,
        }
    finally:
        connection.close()
