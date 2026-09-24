"""Owner-scoped local demo job queue.

Jobs live in their own SQLite database, apart from the engine journal, so web lifecycle
state never enters an engine run manifest. One host and one worker only: WAL, a busy
timeout and ``BEGIN IMMEDIATE`` transactions serialize submits, claims and transitions.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .read_service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, DemoNotFound, envelope
from .replay_catalog import build_replay_request, request_fingerprint, validated_request_fields


ACTIVE_STATES = ("running", "cancel_requested")
PHASES = ("validating", "replaying", "exporting", "verifying")
# Summaries are fixed per code so no worker text (paths, tracebacks, credentials) can
# reach the API. Details belong in a private, sanitized log artifact.
FAILURE_SUMMARIES = {
    "validation_failed": "The run request no longer passes validation.",
    "input_unavailable": "The approved dataset could not be read.",
    "timeout": "The replay exceeded its time limit.",
    "worker_lost": "The worker stopped reporting before the run finished.",
    "execution_failed": "The replay did not finish successfully.",
    "artifact_invalid": "The replay output failed verification.",
}
MAX_ATTEMPTS = 2
REQUESTER_NAMESPACE = uuid.UUID("3c0f6f0e-8f5e-4b53-9c7a-1d2b6f4a9e21")


class IdempotencyConflict(ValueError):
    """The owner reused an idempotency key for a different run request."""


class LeaseLost(RuntimeError):
    """The caller no longer holds the job's lease, or the job left an active state."""


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    lease_token: str
    attempt: int
    request: Dict[str, Any]
    normalized_run: Dict[str, Any]
    strategy_configuration: Dict[str, Any]


def _available(value: Any, detail: Optional[str] = None) -> Dict[str, Any]:
    return {"availability": "available", "value": value, "reason": None, "detail": detail}


def _unavailable(reason: str, detail: str) -> Dict[str, Any]:
    return {"availability": "unavailable", "value": None, "reason": reason, "detail": detail}


def _canonical_job_id(value: Any) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise DemoNotFound("Unknown run") from exc
    if str(parsed) != value:
        raise DemoNotFound("Unknown run")
    return value


def _page_size(value: Optional[str]) -> int:
    if value is None:
        return DEFAULT_PAGE_SIZE
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError("limit must be between 1 and %d" % MAX_PAGE_SIZE)
    return limit


def _lease_duration(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("lease_seconds must be a positive number")
    return float(value)


def requester_id_for(owner_id: str) -> str:
    # The status contract needs a UUID requester; the local operator scope is a name.
    return str(uuid.uuid5(REQUESTER_NAMESPACE, owner_id))


class JobStore:
    def __init__(self, db_path: Path | str, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.db_path = Path(db_path)
        self.clock = clock
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def _now(self) -> Tuple[str, float]:
        # Call only inside _transaction: a time read before a lock wait can precede the
        # writes that commit during that wait, breaking created <= started <= ended.
        now = self.clock()
        return now.isoformat(), now.timestamp()

    def init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS demo_jobs (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    owner_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    normalized_run_json TEXT NOT NULL,
                    strategy_configuration_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN
                        ('queued','running','cancel_requested','completed','failed','cancelled')),
                    phase TEXT CHECK (phase IS NULL OR phase IN
                        ('validating','replaying','exporting','verifying')),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    heartbeat_at TEXT,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    lease_expires_at REAL,
                    engine_run_id TEXT,
                    result_id TEXT,
                    failure_json TEXT,
                    cancel_requested_at TEXT,
                    cancel_requester_id TEXT,
                    UNIQUE (owner_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS demo_jobs_owner_seq ON demo_jobs(owner_id, seq);
                CREATE INDEX IF NOT EXISTS demo_jobs_state_seq ON demo_jobs(state, seq);
                """
            )
        finally:
            conn.close()

    def submit(self, owner_id: str, request: Any) -> Tuple[str, bool]:
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("A configured demo owner is required")
        fields = validated_request_fields(request)
        fingerprint = request_fingerprint(fields)
        # A repeat click returns its run without re-reading the dataset, so it still gets
        # the same run after the dataset changes and skips the costly bar load.
        conn = self._connect()
        try:
            existing_id = self._job_for_key(conn, owner_id, fields["idempotency_key"], fingerprint)
        finally:
            conn.close()
        if existing_id is not None:
            return existing_id, False
        built = build_replay_request(fields)
        with self._transaction() as conn:
            created_at, _ = self._now()
            existing_id = self._job_for_key(conn, owner_id, fields["idempotency_key"], fingerprint)
            if existing_id is not None:
                return existing_id, False
            job_id = built.normalized_run["id"]
            conn.execute(
                """INSERT INTO demo_jobs (id, owner_id, idempotency_key, request_fingerprint, request_json,
                       normalized_run_json, strategy_configuration_json, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)""",
                (job_id, owner_id, built.idempotency_key, built.request_fingerprint,
                 json.dumps(fields, sort_keys=True), json.dumps(built.normalized_run, sort_keys=True),
                 json.dumps(built.strategy_configuration, sort_keys=True), created_at),
            )
        return job_id, True

    @staticmethod
    def _job_for_key(conn: sqlite3.Connection, owner_id: str, idempotency_key: str,
                     fingerprint: str) -> Optional[str]:
        existing = conn.execute(
            "SELECT id, request_fingerprint FROM demo_jobs WHERE owner_id=? AND idempotency_key=?",
            (owner_id, idempotency_key),
        ).fetchone()
        if existing is None:
            return None
        if existing["request_fingerprint"] != fingerprint:
            raise IdempotencyConflict("idempotency_key was already used for a different request")
        return existing["id"]

    def _owned_row(self, conn: sqlite3.Connection, owner_id: str, job_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM demo_jobs WHERE id=? AND owner_id=?",
                           (_canonical_job_id(job_id), owner_id)).fetchone()
        if row is None:
            raise DemoNotFound("Unknown run")
        return row

    def list_jobs(self, owner_id: str, *, limit: Optional[str] = None,
                  cursor: Optional[str] = None) -> Dict[str, Any]:
        page_size = _page_size(limit)
        conn = self._connect()
        try:
            before_seq = None
            if cursor is not None:
                try:
                    before_seq = self._owned_row(conn, owner_id, cursor)["seq"]
                except DemoNotFound as exc:
                    raise ValueError("cursor is not a run in this scope") from exc
            sql = "SELECT * FROM demo_jobs WHERE owner_id=?"
            params: List[Any] = [owner_id]
            if before_seq is not None:
                sql += " AND seq<?"
                params.append(before_seq)
            sql += " ORDER BY seq DESC LIMIT ?"
            params.append(page_size + 1)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        return envelope({"runs": [self._status(row) for row in rows],
                         "next_cursor": rows[-1]["id"] if has_more else None})

    def job_detail(self, owner_id: str, job_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = self._owned_row(conn, owner_id, job_id)
        finally:
            conn.close()
        return envelope({"run": json.loads(row["normalized_run_json"]), "status": self._status(row)})

    def request_cancel(self, owner_id: str, job_id: str) -> Dict[str, Any]:
        with self._transaction() as conn:
            requested_at, _ = self._now()
            row = self._owned_row(conn, owner_id, job_id)
            if row["state"] == "queued":
                conn.execute(
                    """UPDATE demo_jobs SET state='cancelled', ended_at=?, cancel_requested_at=?,
                           cancel_requester_id=? WHERE id=?""",
                    (requested_at, requested_at, requester_id_for(owner_id), row["id"]),
                )
            elif row["state"] == "running":
                conn.execute(
                    """UPDATE demo_jobs SET state='cancel_requested', cancel_requested_at=?,
                           cancel_requester_id=? WHERE id=?""",
                    (requested_at, requester_id_for(owner_id), row["id"]),
                )
        return self.job_detail(owner_id, job_id)

    def claim_next(self, *, lease_seconds: float) -> Optional[ClaimedJob]:
        lease_seconds = _lease_duration(lease_seconds)
        lease_token = str(uuid.uuid4())
        with self._transaction() as conn:
            started_at, now = self._now()
            row = conn.execute("SELECT * FROM demo_jobs WHERE state='queued' ORDER BY seq LIMIT 1").fetchone()
            if row is None:
                return None
            conn.execute(
                """UPDATE demo_jobs SET state='running', phase='validating', started_at=?, heartbeat_at=?,
                       attempt=attempt+1, lease_token=?, lease_expires_at=? WHERE id=? AND state='queued'""",
                (started_at, started_at, lease_token, now + lease_seconds, row["id"]),
            )
        return ClaimedJob(id=row["id"], lease_token=lease_token, attempt=row["attempt"] + 1,
                          request=json.loads(row["request_json"]),
                          normalized_run=json.loads(row["normalized_run_json"]),
                          strategy_configuration=json.loads(row["strategy_configuration_json"]))

    def _leased_row(self, conn: sqlite3.Connection, job_id: str, lease_token: str, now: float) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM demo_jobs WHERE id=? AND lease_token=?",
                           (job_id, lease_token)).fetchone()
        if row is None or row["state"] not in ACTIVE_STATES or row["lease_expires_at"] < now:
            raise LeaseLost("Job %s is no longer leased to this worker" % job_id)
        return row

    def heartbeat(self, job_id: str, lease_token: str, *, lease_seconds: float,
                  phase: Optional[str] = None) -> str:
        if phase is not None and phase not in PHASES:
            raise ValueError("Unknown phase: %s" % phase)
        lease_seconds = _lease_duration(lease_seconds)
        with self._transaction() as conn:
            heartbeat_at, now = self._now()
            row = self._leased_row(conn, job_id, lease_token, now)
            conn.execute(
                "UPDATE demo_jobs SET heartbeat_at=?, lease_expires_at=?, phase=COALESCE(?, phase) WHERE id=?",
                (heartbeat_at, now + lease_seconds, phase, job_id),
            )
        return row["state"]

    def complete(self, job_id: str, lease_token: str, *, engine_run_id: str, result_id: str) -> None:
        if not isinstance(engine_run_id, str) or not engine_run_id:
            raise ValueError("engine_run_id is required")
        result_id = str(uuid.UUID(result_id))
        with self._transaction() as conn:
            ended_at, now = self._now()
            self._leased_row(conn, job_id, lease_token, now)
            # Completion wins over a pending cancel: the result was already published.
            conn.execute(
                """UPDATE demo_jobs SET state='completed', ended_at=?, engine_run_id=?, result_id=?,
                       lease_token=NULL, lease_expires_at=NULL WHERE id=?""",
                (ended_at, engine_run_id, result_id, job_id),
            )

    def fail(self, job_id: str, lease_token: str, *, code: str, retryable: bool = False) -> None:
        with self._transaction() as conn:
            ended_at, now = self._now()
            failure = self._failure(code, ended_at, retryable)
            self._leased_row(conn, job_id, lease_token, now)
            conn.execute(
                """UPDATE demo_jobs SET state='failed', ended_at=?, failure_json=?,
                       lease_token=NULL, lease_expires_at=NULL WHERE id=?""",
                (ended_at, json.dumps(failure), job_id),
            )

    def confirm_cancelled(self, job_id: str, lease_token: str) -> None:
        with self._transaction() as conn:
            ended_at, now = self._now()
            row = self._leased_row(conn, job_id, lease_token, now)
            if row["state"] != "cancel_requested":
                raise LeaseLost("Job %s has no pending cancel request" % job_id)
            conn.execute(
                """UPDATE demo_jobs SET state='cancelled', ended_at=?,
                       lease_token=NULL, lease_expires_at=NULL WHERE id=?""",
                (ended_at, job_id),
            )

    def recover_expired_leases(self) -> Dict[str, str]:
        outcomes: Dict[str, str] = {}
        with self._transaction() as conn:
            recovered_at, now = self._now()
            expired = conn.execute(
                "SELECT id, state, attempt FROM demo_jobs WHERE state IN (?, ?) AND lease_expires_at < ?",
                (*ACTIVE_STATES, now),
            ).fetchall()
            for row in expired:
                if row["state"] == "cancel_requested":
                    conn.execute(
                        """UPDATE demo_jobs SET state='cancelled', ended_at=?,
                               lease_token=NULL, lease_expires_at=NULL WHERE id=?""",
                        (recovered_at, row["id"]),
                    )
                    outcomes[row["id"]] = "cancelled"
                elif row["attempt"] < MAX_ATTEMPTS:
                    # A replay writes nothing public until complete() records its result, so
                    # an unfinished attempt can safely run once more in a fresh directory.
                    conn.execute(
                        """UPDATE demo_jobs SET state='queued', phase=NULL, started_at=NULL, heartbeat_at=NULL,
                               lease_token=NULL, lease_expires_at=NULL WHERE id=?""",
                        (row["id"],),
                    )
                    outcomes[row["id"]] = "queued"
                else:
                    failure = self._failure("worker_lost", recovered_at, False)
                    conn.execute(
                        """UPDATE demo_jobs SET state='failed', ended_at=?, failure_json=?,
                               lease_token=NULL, lease_expires_at=NULL WHERE id=?""",
                        (recovered_at, json.dumps(failure), row["id"]),
                    )
                    outcomes[row["id"]] = "failed"
        return outcomes

    @staticmethod
    def _failure(code: str, at: str, retryable: bool) -> Dict[str, Any]:
        if code not in FAILURE_SUMMARIES:
            raise ValueError("Unknown failure code: %s" % code)
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")
        return {"code": code, "summary": FAILURE_SUMMARIES[code], "at": at,
                "retryable": retryable,
                "log_artifact_id": _unavailable("not_recorded", "No log artifact is published for this job.")}

    @staticmethod
    def _status(row: sqlite3.Row) -> Dict[str, Any]:
        def recorded(column: str, missing: str) -> Dict[str, Any]:
            return _available(row[column]) if row[column] is not None else _unavailable("not_applicable", missing)

        state = row["state"]
        if row["cancel_requested_at"] is not None:
            cancellation = {"requested_at": row["cancel_requested_at"], "requester_id": row["cancel_requester_id"]}
        else:
            cancellation = _unavailable("not_applicable", "No cancellation was requested.")
        return {
            "record_type": "status", "run_id": row["id"], "origin": "job", "state": state,
            "created_at": _available(row["created_at"]),
            "started_at": recorded("started_at", "The job has not started."),
            "ended_at": recorded("ended_at", "The job has not ended."),
            "phase": recorded("phase", "No worker phase is reported."),
            "progress": _unavailable("not_recorded", "The replay does not report trustworthy progress counts."),
            "heartbeat_at": recorded("heartbeat_at", "No worker heartbeat is recorded."),
            "attempt": _available(row["attempt"]),
            "engine_run_id": recorded("engine_run_id", "No engine run is recorded."),
            "result_id": (_available(row["result_id"]) if state == "completed"
                          else _unavailable("not_applicable", "Only a completed job has a result.")),
            "failure": (json.loads(row["failure_json"]) if state == "failed"
                        else _unavailable("not_applicable", "The job has not failed.")),
            "cancellation": cancellation,
        }
