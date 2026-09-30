"""PostgreSQL C3 job authority. Connections are supplied by the hosted deployment.

API methods run inside ``PostgresIdentity.transaction``; worker methods run with the
separate ``hosted_worker`` database role. This module never opens local SQLite or a
broker client. Each method is one transaction on the caller's connection.
"""
import hashlib
import json
import uuid

from .hosted_identity import BoundaryDenied


FAILURE_CODES = frozenset({"validation_failed", "input_unavailable", "timeout",
                           "worker_lost", "execution_failed", "artifact_invalid"})
PHASES = frozenset({"validating", "replaying", "exporting", "verifying"})
PHASE_ORDER = {name: index for index, name in enumerate(
    ("validating", "replaying", "exporting", "verifying"))}
MAX_ATTEMPTS = 2


class LeaseLost(RuntimeError):
    pass


class IdempotencyConflict(ValueError):
    pass


def _uuid(value):
    try:
        parsed = str(uuid.UUID(value))
    except (TypeError, AttributeError, ValueError):
        raise ValueError("Canonical UUID required") from None
    if parsed != value:
        raise ValueError("Canonical UUID required")
    return value


def _sha256(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("SHA-256 hex required")
    return value


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3600:
        raise ValueError("Lease seconds must be an integer from 1 to 3600")
    return value


def _json(value):
    # psycopg adapters can bind this as jsonb using an explicit cast. No paths or
    # credentials should be placed in a request document by its caller.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class HostedJobStore:
    """Small transaction-scoped operations; no connection pool or implicit commit."""

    @staticmethod
    def existing(conn, scope, key, request_hash, configuration_hash):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError("Invalid idempotency key")
        _sha256(request_hash)
        _sha256(configuration_hash)
        row = conn.execute(
            "SELECT id,request_hash,configuration_hash FROM hosted_runs "
            "WHERE tenant_id=%s AND idempotency_key=%s FOR UPDATE",
            (scope.tenant_id, key)).fetchone()
        if row is None:
            return None
        if (row[1], row[2]) != (request_hash, configuration_hash):
            raise IdempotencyConflict("idempotency_key_conflict")
        return str(row[0])

    def submit(self, conn, scope, *, key, request_hash, configuration_hash, request_document,
               configuration_document, run_id=None):
        """Call ``existing`` before expensive request normalization, then submit.

        The unique index resolves concurrent submits. The losing transaction reads
        the winner after the unique-index wait at READ COMMITTED isolation.
        """
        scope.require_write()
        if hash_document(request_document) != request_hash or hash_document(configuration_document) != configuration_hash:
            raise ValueError("Document hash mismatch")
        known = self.existing(conn, scope, key, request_hash, configuration_hash)
        if known:
            return known, False
        run_id = _uuid(run_id) if run_id is not None else str(uuid.uuid4())
        document = _json(request_document)
        configuration = _json(configuration_document)
        conn.execute("SAVEPOINT hosted_submit")
        row = conn.execute(
            "INSERT INTO hosted_resources (tenant_id,id,kind) VALUES (%s,%s,'run') "
            "ON CONFLICT DO NOTHING RETURNING id", (scope.tenant_id, run_id)).fetchone()
        if row is None:
            raise ValueError("Run ID already exists")
        inserted = conn.execute(
            "INSERT INTO hosted_runs (tenant_id,id,requester_id,idempotency_key,request_hash,"
            "configuration_hash,request_json,configuration_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
            "ON CONFLICT (tenant_id,idempotency_key) DO NOTHING RETURNING id",
            (scope.tenant_id, run_id, scope.user_id, key, request_hash,
             configuration_hash, document, configuration)).fetchone()
        if inserted is None:
            # Undo the newly inserted registry row without granting DELETE to API roles.
            conn.execute("ROLLBACK TO SAVEPOINT hosted_submit")
            conn.execute("RELEASE SAVEPOINT hosted_submit")
            winner = self.existing(conn, scope, key, request_hash, configuration_hash)
            if winner is None:
                raise RuntimeError("Concurrent submission disappeared")
            return winner, False
        conn.execute("INSERT INTO hosted_outbox (tenant_id,run_id,kind) VALUES (%s,%s,'run_queued')",
                     (scope.tenant_id, run_id))
        conn.execute("RELEASE SAVEPOINT hosted_submit")
        return run_id, True

    @staticmethod
    def cancel(conn, scope, run_id):
        scope.require_write()
        run_id = _uuid(run_id)
        row = conn.execute("SELECT state FROM hosted_runs WHERE tenant_id=%s AND id=%s FOR UPDATE",
                           (scope.tenant_id, run_id)).fetchone()
        if row is None:
            raise BoundaryDenied("not_found", 404)
        if row[0] == "queued":
            conn.execute("UPDATE hosted_runs SET state='cancelled',cancel_requested_at=clock_timestamp(),"
                         "ended_at=clock_timestamp() WHERE tenant_id=%s AND id=%s",
                         (scope.tenant_id, run_id))
        elif row[0] == "running":
            conn.execute("UPDATE hosted_runs SET state='cancel_requested',"
                         "cancel_requested_at=clock_timestamp() WHERE tenant_id=%s AND id=%s",
                         (scope.tenant_id, run_id))
        return row[0]

    @staticmethod
    def claim_next(conn, *, lease_seconds):
        lease_seconds = _seconds(lease_seconds)
        # Lock in the same transaction as the state and attempt writes. Competing
        # workers skip this row; one run can have only one current lease.
        row = conn.execute(
            "SELECT tenant_id,id,attempt,request_json,configuration_json FROM hosted_runs WHERE state='queued' "
            "ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if row is None:
            return None
        tenant_id, run_id, attempt, document, configuration = row
        token = str(uuid.uuid4())
        number = attempt + 1
        conn.execute("UPDATE hosted_runs SET state='running',attempt=%s,"
                     "started_at=COALESCE(started_at,clock_timestamp()) "
                     "WHERE tenant_id=%s AND id=%s", (number, tenant_id, run_id))
        conn.execute(
            "INSERT INTO hosted_run_attempts (tenant_id,run_id,number,lease_token,phase,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,'validating',clock_timestamp()+(%s * interval '1 second'))",
            (tenant_id, run_id, number, token, lease_seconds))
        return {"tenant_id": str(tenant_id), "run_id": str(run_id), "attempt": number,
                "lease_token": token, "request": document, "configuration": configuration}

    @staticmethod
    def heartbeat(conn, *, tenant_id, run_id, lease_token, lease_seconds, phase=None):
        _uuid(tenant_id); _uuid(run_id); _uuid(lease_token)
        lease_seconds = _seconds(lease_seconds)
        if phase is not None and phase not in PHASES:
            raise ValueError("Unknown phase")
        row = HostedJobStore._current(conn, tenant_id, run_id, lease_token)
        if phase is not None and PHASE_ORDER[phase] < PHASE_ORDER[row[4]]:
            raise ValueError("Phase cannot move backward")
        conn.execute("UPDATE hosted_run_attempts SET heartbeat_at=clock_timestamp(),"
                     "lease_expires_at=clock_timestamp()+(%s * interval '1 second'),"
                     "phase=COALESCE(%s,phase) WHERE tenant_id=%s AND run_id=%s AND number=%s",
                     (lease_seconds, phase, tenant_id, run_id, row[1]))
        return row[0]

    @staticmethod
    def _current(conn, tenant_id, run_id, lease_token, *, allow_expired=False):
        row = conn.execute(
            "SELECT r.state,r.attempt,a.lease_expires_at,a.ended_at,a.phase FROM hosted_runs r "
            "JOIN hosted_run_attempts a ON (a.tenant_id,a.run_id,a.number)=(r.tenant_id,r.id,r.attempt) "
            "WHERE r.tenant_id=%s AND r.id=%s AND a.lease_token=%s FOR UPDATE OF r,a",
            (_uuid(tenant_id), _uuid(run_id), _uuid(lease_token))).fetchone()
        if (row is None or row[0] not in ("running", "cancel_requested") or row[3] is not None or
                (not allow_expired and conn.execute("SELECT %s < clock_timestamp()", (row[2],)).fetchone()[0])):
            raise LeaseLost("Lease unavailable")
        return row

    def complete(self, conn, *, tenant_id, run_id, lease_token, result_id, content_hash,
                 result_document, artifacts=()):
        """Publish metadata and completion atomically; object bytes belong to C4."""
        _uuid(tenant_id); _uuid(run_id); _uuid(lease_token); _uuid(result_id); _sha256(content_hash)
        artifacts = tuple(artifacts)
        if (not isinstance(result_document, dict) or result_document.get("id") != result_id or
                result_document.get("run_id") != run_id or
                result_document.get("artifact_ids") != [item.get("id") for item in artifacts]):
            raise ValueError("Result identity mismatch")
        result_document = _json(result_document)
        published = conn.execute(
            "SELECT x.id,x.content_hash,r.state FROM hosted_results x "
            "JOIN hosted_runs r ON (r.tenant_id,r.id)=(x.tenant_id,x.run_id) "
            "JOIN hosted_run_attempts a ON (a.tenant_id,a.run_id,a.number)="
            "(x.tenant_id,x.run_id,x.attempt) "
            "WHERE x.tenant_id=%s AND x.run_id=%s AND a.lease_token=%s",
            (tenant_id, run_id, lease_token)).fetchone()
        if published is not None:
            if (str(published[0]), published[1], published[2]) != (result_id, content_hash, "completed"):
                raise ValueError("Conflicting publication")
            return False
        row = self._current(conn, tenant_id, run_id, lease_token, allow_expired=True)
        prior = conn.execute("SELECT id,content_hash FROM hosted_results WHERE tenant_id=%s AND run_id=%s",
                             (tenant_id, run_id)).fetchone()
        if prior is not None:
            if (str(prior[0]), prior[1]) != (result_id, content_hash):
                raise ValueError("Conflicting publication")
            return False
        conn.execute("INSERT INTO hosted_resources (tenant_id,id,kind,parent_id,parent_kind) "
                     "VALUES (%s,%s,'result',%s,'run')", (tenant_id, result_id, run_id))
        conn.execute("INSERT INTO hosted_results (tenant_id,id,run_id,attempt,content_hash,result_json) "
                     "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                     (tenant_id, result_id, run_id, row[1], content_hash, result_document))
        for artifact in artifacts:
            artifact_id = _uuid(artifact["id"])
            digest = _sha256(artifact["sha256"])
            byte_size = artifact["byte_size"]
            if (not isinstance(byte_size, int) or isinstance(byte_size, bool) or
                    not 0 <= byte_size <= 1048576 or artifact["mime_type"] not in
                    {"application/json", "text/plain", "text/csv"} or
                    not isinstance(artifact["kind"], str) or not 1 <= len(artifact["kind"]) <= 64 or
                    not isinstance(artifact["object_version"], str) or
                    not 1 <= len(artifact["object_version"]) <= 255):
                raise ValueError("Invalid artifact metadata")
            conn.execute("INSERT INTO hosted_resources (tenant_id,id,kind,parent_id,parent_kind) "
                         "VALUES (%s,%s,'artifact',%s,'result')",
                         (tenant_id, artifact_id, result_id))
            conn.execute("INSERT INTO hosted_result_artifacts "
                         "(tenant_id,id,result_id,kind,object_version,sha256,mime_type,byte_size) "
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (tenant_id, artifact_id, result_id, artifact["kind"],
                          artifact["object_version"], digest, artifact["mime_type"], byte_size))
        conn.execute("UPDATE hosted_run_attempts SET ended_at=clock_timestamp() "
                     "WHERE tenant_id=%s AND run_id=%s AND number=%s",
                     (tenant_id, run_id, row[1]))
        conn.execute("UPDATE hosted_runs SET state='completed',ended_at=clock_timestamp() "
                     "WHERE tenant_id=%s AND id=%s", (tenant_id, run_id))
        return True

    def fail(self, conn, *, tenant_id, run_id, lease_token, code):
        if code not in FAILURE_CODES:
            raise ValueError("Unknown failure code")
        row = self._current(conn, tenant_id, run_id, lease_token)
        conn.execute("UPDATE hosted_run_attempts SET ended_at=clock_timestamp(),failure_code=%s "
                     "WHERE tenant_id=%s AND run_id=%s AND number=%s",
                     (code, tenant_id, run_id, row[1]))
        state = "cancelled" if row[0] == "cancel_requested" else "failed"
        conn.execute("UPDATE hosted_runs SET state=%s,ended_at=clock_timestamp(),failure_code=%s "
                     "WHERE tenant_id=%s AND id=%s", (state, code, tenant_id, run_id))
        if state == "failed":
            conn.execute("INSERT INTO hosted_dead_letters (tenant_id,run_id,failure_code) "
                         "VALUES (%s,%s,%s) ON CONFLICT (tenant_id,run_id) DO NOTHING",
                         (tenant_id, run_id, code))
        return state

    def confirm_cancelled(self, conn, *, tenant_id, run_id, lease_token):
        row = self._current(conn, tenant_id, run_id, lease_token)
        if row[0] != "cancel_requested":
            raise LeaseLost("No cancellation requested")
        conn.execute("UPDATE hosted_run_attempts SET ended_at=clock_timestamp() "
                     "WHERE tenant_id=%s AND run_id=%s AND number=%s",
                     (tenant_id, run_id, row[1]))
        conn.execute("UPDATE hosted_runs SET state='cancelled',ended_at=clock_timestamp() "
                     "WHERE tenant_id=%s AND id=%s", (tenant_id, run_id))

    @staticmethod
    def recover_expired(conn, *, limit=100):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Invalid recovery limit")
        rows = conn.execute(
            "SELECT r.tenant_id,r.id,r.state,r.attempt FROM hosted_runs r "
            "JOIN hosted_run_attempts a ON (a.tenant_id,a.run_id,a.number)=(r.tenant_id,r.id,r.attempt) "
            "WHERE r.state IN ('running','cancel_requested') AND a.ended_at IS NULL "
            "AND a.lease_expires_at<clock_timestamp() "
            "ORDER BY a.lease_expires_at FOR UPDATE OF r,a SKIP LOCKED LIMIT %s", (limit,)).fetchall()
        outcomes = []
        for tenant_id, run_id, state, attempt in rows:
            # Publication and state change share a transaction; a visible result wins.
            published = conn.execute("SELECT 1 FROM hosted_results WHERE tenant_id=%s AND run_id=%s",
                                     (tenant_id, run_id)).fetchone()
            if published:
                next_state = "completed"
            elif state == "cancel_requested":
                next_state = "cancelled"
            elif attempt < MAX_ATTEMPTS:
                next_state = "queued"
            else:
                next_state = "failed"
            conn.execute("UPDATE hosted_run_attempts SET ended_at=clock_timestamp(),"
                         "failure_code=CASE WHEN %s='failed' THEN 'worker_lost' ELSE failure_code END "
                         "WHERE tenant_id=%s AND run_id=%s AND number=%s",
                         (next_state, tenant_id, run_id, attempt))
            conn.execute("UPDATE hosted_runs SET state=%s,"
                         "ended_at=CASE WHEN %s='queued' THEN NULL ELSE clock_timestamp() END,"
                         "failure_code=CASE WHEN %s='failed' THEN 'worker_lost' ELSE failure_code END "
                         "WHERE tenant_id=%s AND id=%s",
                         (next_state, next_state, next_state, tenant_id, run_id))
            if next_state == "failed":
                conn.execute("INSERT INTO hosted_dead_letters (tenant_id,run_id,failure_code) "
                             "VALUES (%s,%s,'worker_lost') ON CONFLICT (tenant_id,run_id) DO NOTHING",
                             (tenant_id, run_id))
            outcomes.append((str(run_id), next_state))
        return outcomes

    @staticmethod
    def pending_outbox(conn, *, limit=100):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Invalid outbox limit")
        return conn.execute("SELECT id,tenant_id,run_id FROM hosted_outbox "
                            "WHERE delivered_at IS NULL ORDER BY id FOR UPDATE SKIP LOCKED LIMIT %s",
                            (limit,)).fetchall()

    @staticmethod
    def mark_delivered(conn, outbox_id):
        conn.execute("UPDATE hosted_outbox SET delivered_at=clock_timestamp() "
                     "WHERE id=%s AND delivered_at IS NULL", (outbox_id,))


def hash_document(document):
    return hashlib.sha256(_json(document).encode("utf-8")).hexdigest()
