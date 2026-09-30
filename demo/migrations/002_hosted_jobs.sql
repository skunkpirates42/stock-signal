-- C3 hosted authority. Apply after 001 with a migration role. The deployment must
-- provision a NOLOGIN hosted_worker role and give only its worker login membership.
-- API logins must never inherit hosted_worker. Local demo SQLite is untouched.
BEGIN;
ALTER TABLE hosted_resources ADD CONSTRAINT hosted_resources_parent_identity
    UNIQUE (tenant_id,id,kind,parent_id,parent_kind);
CREATE TABLE hosted_runs (
    tenant_id uuid NOT NULL REFERENCES hosted_tenants(id),
    id uuid NOT NULL,
    requester_id uuid NOT NULL REFERENCES hosted_users(id),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    configuration_hash text NOT NULL CHECK (configuration_hash ~ '^[0-9a-f]{64}$'),
    request_json jsonb NOT NULL, configuration_json jsonb NOT NULL,
    resource_kind text NOT NULL DEFAULT 'run' CHECK (resource_kind='run'),
    state text NOT NULL DEFAULT 'queued' CHECK (state IN
        ('queued','running','cancel_requested','completed','failed','cancelled')),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 2),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz, ended_at timestamptz, cancel_requested_at timestamptz,
    failure_code text CHECK (failure_code IN ('validation_failed','input_unavailable',
        'timeout','worker_lost','execution_failed','artifact_invalid')),
    PRIMARY KEY (tenant_id,id), UNIQUE (tenant_id,idempotency_key),
    FOREIGN KEY (tenant_id,id,resource_kind) REFERENCES hosted_resources(tenant_id,id,kind)
);
CREATE INDEX hosted_runs_queue ON hosted_runs(created_at,id) WHERE state='queued';
CREATE INDEX hosted_runs_tenant_list ON hosted_runs(tenant_id,created_at DESC,id DESC);
CREATE TABLE hosted_run_attempts (
    tenant_id uuid NOT NULL, run_id uuid NOT NULL, number integer NOT NULL CHECK (number BETWEEN 1 AND 2),
    lease_token uuid NOT NULL UNIQUE, phase text NOT NULL CHECK (phase IN
        ('validating','replaying','exporting','verifying')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    heartbeat_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_expires_at timestamptz NOT NULL,
    ended_at timestamptz,
    failure_code text CHECK (failure_code IN ('validation_failed','input_unavailable',
        'timeout','worker_lost','execution_failed','artifact_invalid')),
    PRIMARY KEY (tenant_id,run_id,number),
    FOREIGN KEY (tenant_id,run_id) REFERENCES hosted_runs(tenant_id,id)
);
CREATE TABLE hosted_results (
    tenant_id uuid NOT NULL, id uuid NOT NULL, run_id uuid NOT NULL,
    resource_kind text NOT NULL DEFAULT 'result' CHECK (resource_kind='result'),
    resource_parent_kind text NOT NULL DEFAULT 'run' CHECK (resource_parent_kind='run'),
    attempt integer NOT NULL, content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    result_json jsonb NOT NULL, published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,id), UNIQUE (tenant_id,run_id),
    FOREIGN KEY (tenant_id,run_id,attempt) REFERENCES hosted_run_attempts(tenant_id,run_id,number),
    FOREIGN KEY (tenant_id,id,resource_kind,run_id,resource_parent_kind)
        REFERENCES hosted_resources(tenant_id,id,kind,parent_id,parent_kind)
);
CREATE TABLE hosted_result_artifacts (
    tenant_id uuid NOT NULL, id uuid NOT NULL, result_id uuid NOT NULL,
    resource_kind text NOT NULL DEFAULT 'artifact' CHECK (resource_kind='artifact'),
    resource_parent_kind text NOT NULL DEFAULT 'result' CHECK (resource_parent_kind='result'),
    kind text NOT NULL, object_version text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    mime_type text NOT NULL CHECK (mime_type IN ('application/json','text/plain','text/csv')),
    byte_size bigint NOT NULL CHECK (byte_size BETWEEN 0 AND 1048576),
    PRIMARY KEY (tenant_id,id),
    FOREIGN KEY (tenant_id,result_id) REFERENCES hosted_results(tenant_id,id),
    FOREIGN KEY (tenant_id,id,resource_kind,result_id,resource_parent_kind)
        REFERENCES hosted_resources(tenant_id,id,kind,parent_id,parent_kind)
);
CREATE TABLE hosted_outbox (
    id bigserial PRIMARY KEY, tenant_id uuid NOT NULL, run_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind='run_queued'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    delivered_at timestamptz,
    UNIQUE (tenant_id,run_id,kind),
    FOREIGN KEY (tenant_id,run_id) REFERENCES hosted_runs(tenant_id,id)
);
CREATE TABLE hosted_dead_letters (
    tenant_id uuid NOT NULL, run_id uuid NOT NULL,
    failure_code text NOT NULL CHECK (failure_code IN ('validation_failed','input_unavailable',
        'timeout','worker_lost','execution_failed','artifact_invalid')),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,run_id),
    FOREIGN KEY (tenant_id,run_id) REFERENCES hosted_runs(tenant_id,id)
);

ALTER TABLE hosted_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE hosted_run_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_run_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE hosted_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_results FORCE ROW LEVEL SECURITY;
ALTER TABLE hosted_result_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_result_artifacts FORCE ROW LEVEL SECURITY;
ALTER TABLE hosted_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE hosted_dead_letters ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_dead_letters FORCE ROW LEVEL SECURITY;

-- Worker policies are bound to a database role, never to a client-settable GUC.
-- The API's SELECT policy still requires both transaction-local claims and membership.
CREATE POLICY run_api_select ON hosted_runs FOR SELECT USING (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_memberships m WHERE m.tenant_id=hosted_runs.tenant_id
        AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid));
CREATE POLICY run_api_insert ON hosted_runs FOR INSERT WITH CHECK (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    requester_id=nullif(current_setting('app.user_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_memberships m WHERE m.tenant_id=hosted_runs.tenant_id
        AND m.user_id=requester_id AND m.role IN ('owner','operator')));
CREATE POLICY run_api_update ON hosted_runs FOR UPDATE USING (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_memberships m WHERE m.tenant_id=hosted_runs.tenant_id
        AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid
        AND m.role IN ('owner','operator')))
    WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY run_worker ON hosted_runs FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY attempts_worker ON hosted_run_attempts FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY attempts_api_select ON hosted_run_attempts FOR SELECT USING (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_memberships m WHERE m.tenant_id=hosted_run_attempts.tenant_id
        AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid));
CREATE POLICY outbox_worker ON hosted_outbox FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY dead_worker ON hosted_dead_letters FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY result_worker ON hosted_results FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY artifact_worker ON hosted_result_artifacts FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY resource_worker ON hosted_resources FOR ALL TO hosted_worker USING (true) WITH CHECK (true);
CREATE POLICY result_api_select ON hosted_results FOR SELECT USING (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_memberships m WHERE m.tenant_id=hosted_results.tenant_id
        AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid));
CREATE POLICY artifact_api_select ON hosted_result_artifacts FOR SELECT USING (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_memberships m WHERE m.tenant_id=hosted_result_artifacts.tenant_id
        AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid));
CREATE POLICY outbox_api_insert ON hosted_outbox FOR INSERT WITH CHECK (
    tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND
    EXISTS (SELECT 1 FROM hosted_runs r WHERE r.tenant_id=hosted_outbox.tenant_id
        AND r.id=hosted_outbox.run_id AND r.requester_id=nullif(current_setting('app.user_id',true),'')::uuid));

REVOKE ALL ON hosted_runs, hosted_run_attempts, hosted_results,
    hosted_result_artifacts, hosted_outbox, hosted_dead_letters FROM PUBLIC;
GRANT SELECT, UPDATE ON hosted_runs TO hosted_worker;
GRANT INSERT, SELECT, UPDATE ON hosted_run_attempts TO hosted_worker;
GRANT SELECT, UPDATE ON hosted_outbox TO hosted_worker;
GRANT INSERT, SELECT ON hosted_dead_letters, hosted_results,
    hosted_result_artifacts, hosted_resources TO hosted_worker;
GRANT SELECT ON hosted_memberships TO hosted_worker;

-- Immutable identity and publication fields cannot be rewritten by either role.
CREATE FUNCTION hosted_run_immutable() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog AS $$
BEGIN
    IF ROW(NEW.tenant_id,NEW.id,NEW.requester_id,NEW.idempotency_key,
           NEW.request_hash,NEW.configuration_hash,NEW.request_json,
           NEW.configuration_json,NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.tenant_id,OLD.id,OLD.requester_id,OLD.idempotency_key,
           OLD.request_hash,OLD.configuration_hash,OLD.request_json,
           OLD.configuration_json,OLD.created_at) THEN
        RAISE EXCEPTION 'immutable run identity';
    END IF;
    IF OLD.state IN ('completed','failed','cancelled') AND
       ROW(NEW.state,NEW.attempt,NEW.started_at,NEW.ended_at,NEW.failure_code,
           NEW.cancel_requested_at) IS DISTINCT FROM
       ROW(OLD.state,OLD.attempt,OLD.started_at,OLD.ended_at,OLD.failure_code,
           OLD.cancel_requested_at) THEN
        RAISE EXCEPTION 'terminal run is immutable';
    END IF;
    IF NOT pg_catalog.pg_has_role(CURRENT_USER, 'hosted_worker', 'member') THEN
        IF ROW(NEW.attempt,NEW.started_at,NEW.failure_code) IS DISTINCT FROM
           ROW(OLD.attempt,OLD.started_at,OLD.failure_code) OR
           NOT ((NEW.state=OLD.state AND
                 NEW.ended_at IS NOT DISTINCT FROM OLD.ended_at AND
                 NEW.cancel_requested_at IS NOT DISTINCT FROM OLD.cancel_requested_at) OR
                (OLD.state='queued' AND NEW.state='cancelled' AND
                 OLD.ended_at IS NULL AND OLD.cancel_requested_at IS NULL) OR
                (OLD.state='running' AND NEW.state='cancel_requested' AND
                 NEW.ended_at IS NOT DISTINCT FROM OLD.ended_at AND
                 OLD.cancel_requested_at IS NULL)) THEN
            RAISE EXCEPTION 'invalid API transition';
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state THEN
            NEW.cancel_requested_at := pg_catalog.clock_timestamp();
            IF NEW.state='cancelled' THEN
                NEW.ended_at := pg_catalog.clock_timestamp();
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER hosted_run_immutable BEFORE UPDATE ON hosted_runs
    FOR EACH ROW EXECUTE FUNCTION hosted_run_immutable();
CREATE FUNCTION hosted_publication_immutable() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'published metadata is immutable';
END;
$$;
CREATE TRIGGER hosted_result_immutable BEFORE UPDATE OR DELETE ON hosted_results
    FOR EACH ROW EXECUTE FUNCTION hosted_publication_immutable();
CREATE TRIGGER hosted_artifact_immutable BEFORE UPDATE OR DELETE ON hosted_result_artifacts
    FOR EACH ROW EXECUTE FUNCTION hosted_publication_immutable();
COMMIT;
