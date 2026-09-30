"""Administrative provisioning service; never instantiate in web/replay children."""
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .store import Denied, WORKSPACE, canonical_id, migrate, transaction


class TursoPlatform:
    """Platform credentials stay in this administrative process only."""
    def __init__(self, organization, group, token, *, transport=None):
        if any(not re.fullmatch(r"[a-zA-Z0-9_-]+", value) for value in (organization, group)):
            raise ValueError("Invalid provisioner configuration")
        self.organization, self.group, self._token = organization, group, token
        self.transport = transport or self._request

    def _request(self, method, path, body=None):
        request = Request("https://api.turso.tech/v1/organizations/" + self.organization + path,
                          data=None if body is None else json.dumps(body).encode(), method=method,
                          headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=10) as response:
                data = response.read(65537)
                if len(data) > 65536:
                    raise Denied("provisioning_failed", 503)
                return response.status, json.loads(data)
        except HTTPError as exc:
            # Do not read or log remote error bodies/headers.
            return exc.code, {}
        except Exception:
            raise Denied("provisioning_failed", 503) from None

    def ensure_database(self, name):
        if not re.fullmatch(r"ws-[0-9a-f]{32}", name):
            raise Denied("provisioning_failed", 503)
        status, _ = self.transport("POST", "/databases", {"name": name, "group": self.group})
        if status not in {200, 201, 409}:
            raise Denied("provisioning_failed", 503)
        status, body = self.transport("GET", "/databases/" + name)
        database = body.get("database", {})
        hostname = database.get("Hostname", "")
        if status != 200 or database.get("Name") != name or not re.fullmatch(r"[a-zA-Z0-9-]+\.turso\.io", hostname):
            raise Denied("provisioning_failed", 503)
        return "libsql://" + hostname

    def database_token(self, name):
        if not re.fullmatch(r"ws-[0-9a-f]{32}", name):
            raise Denied("provisioning_failed", 503)
        status, body = self.transport("POST", "/databases/" + name + "/auth/tokens?expiration=1d&authorization=full-access", {})
        token = body.get("jwt")
        if status != 200 or not isinstance(token, str) or not token:
            raise Denied("provisioning_failed", 503)
        return token


def remote_connections(secret_store):
    """Direct authoritative remote connections; no embedded replica or sync."""
    def connect(endpoint, secret_ref):
        if not re.fullmatch(r"libsql://[a-zA-Z0-9-]+\.turso\.io", endpoint):
            raise Denied("unavailable", 503)
        import libsql
        return libsql.connect(endpoint, auth_token=secret_store.get(secret_ref), isolation_level=None)
    return connect


class Provisioner:
    def __init__(self, control, platform, secrets, connections):
        self.control, self.platform, self.secrets, self.connections = control, platform, secrets, connections

    def provision(self, workspace):
        canonical_id(workspace)
        with transaction(self.control.connect) as conn:
            row = conn.execute("SELECT state FROM workspaces WHERE id=?", (workspace,)).fetchone()
            if row is None:
                raise Denied("not_found", 404)
            if row[0] != "ready":
                conn.execute("UPDATE workspaces SET state='initializing',failure_code=NULL WHERE id=?", (workspace,))
        # Administrative serialization deliberately spans provisioning. A crash
        # rolls back this control transaction; deterministic name + atomic secret put
        # and atomic migration permit resuming any interrupted external step.
        try:
            with transaction(self.control.connect) as conn:
                row = conn.execute("SELECT database_name,state FROM workspaces WHERE id=?", (workspace,)).fetchone()
                if row is None:
                    raise Denied("not_found", 404)
                if row[1] == "ready":
                    return
                conn.execute("UPDATE workspaces SET state='initializing',failure_code=NULL WHERE id=?", (workspace,))
                endpoint = self.platform.ensure_database(row[0])
                ref = "workspaces/" + workspace + "/database"
                # Refresh on retries too: an interrupted provision may outlive
                # its short-lived database-scoped token. Secret writes must be
                # atomic replacements, never returned to callers.
                self.secrets.put(ref, self.platform.database_token(row[0]))
                migrate(lambda: self.connections(endpoint, ref), WORKSPACE, workspace)
                conn.execute("UPDATE workspaces SET state='ready',endpoint=?,secret_ref=?,schema_version=1 WHERE id=?", (endpoint, ref, workspace))
        except Exception:
            with transaction(self.control.connect) as conn:
                conn.execute("UPDATE workspaces SET state='failed',failure_code='provisioning_failed' WHERE id=? AND state!='ready'", (workspace,))
            raise Denied("provisioning_failed", 503) from None
