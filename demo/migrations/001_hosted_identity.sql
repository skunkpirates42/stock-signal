-- C2 only. Apply using the migration role; the runtime role must not own tables,
-- have BYPASSRLS, or have DDL/TRUNCATE permissions. No local SQLite migration.
BEGIN;
CREATE TABLE hosted_users (
    id uuid PRIMARY KEY, issuer text NOT NULL, subject text NOT NULL,
    UNIQUE (issuer, subject)
);
CREATE TABLE hosted_tenants (id uuid PRIMARY KEY);
CREATE TABLE hosted_memberships (
    tenant_id uuid NOT NULL REFERENCES hosted_tenants(id),
    user_id uuid NOT NULL REFERENCES hosted_users(id),
    role text NOT NULL CHECK (role IN ('owner','operator','viewer')),
    PRIMARY KEY (tenant_id,user_id)
);
ALTER TABLE hosted_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY own_memberships ON hosted_memberships
    FOR SELECT USING (user_id = nullif(current_setting('app.user_id',true),'')::uuid);
-- Administrative membership writes use a separate audited provisioning role.
-- Serialize membership changes against authorized operation transactions without
-- granting those readers UPDATE or an UPDATE RLS policy. Concurrent readers share
-- the lock. Provisioning is infrequent, so one global control-plane lock is enough.
-- No SECURITY DEFINER privileges are needed: advisory locks are available to the
-- provisioning role. Trigger functions cannot be invoked as ordinary SQL functions.
CREATE FUNCTION hosted_membership_write_lock() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(1937010547, 1);
    RETURN NULL;
END;
$$;
CREATE TRIGGER hosted_membership_write_lock
    BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON hosted_memberships
    FOR EACH STATEMENT EXECUTE FUNCTION hosted_membership_write_lock();
-- Privileged maintenance must keep the trigger enabled. Runtime/provisioning roles
-- get no table ownership, trigger-management, TRUNCATE or replication-role powers.
CREATE TABLE hosted_login_challenges (
    id_hash text PRIMARY KEY, nonce text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE hosted_sessions (
    id_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES hosted_users(id),
    csrf_hash text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE hosted_rate_buckets (
    kind text NOT NULL CHECK (kind IN ('user','tenant')), identity uuid NOT NULL,
    bucket timestamptz NOT NULL, count bigint NOT NULL CHECK (count > 0),
    PRIMARY KEY (kind,identity,bucket)
);
-- The C2 authorization registry; C3+ stores reference this composite identity
-- and create these rows in the same transaction as the domain records.
CREATE TABLE hosted_resources (
    tenant_id uuid NOT NULL REFERENCES hosted_tenants(id),
    id uuid NOT NULL, kind text NOT NULL CHECK (kind IN ('run','result','artifact')),
    parent_id uuid, parent_kind text,
    PRIMARY KEY (tenant_id,id), UNIQUE (tenant_id,id,kind),
    FOREIGN KEY (tenant_id,parent_id,parent_kind)
        REFERENCES hosted_resources(tenant_id,id,kind),
    CHECK ((parent_id IS NULL) = (parent_kind IS NULL)),
    CHECK ((kind='run' AND parent_id IS NULL) OR
           (kind='result' AND (parent_kind='run' OR parent_id IS NULL)) OR
           (kind='artifact' AND parent_id IS NOT NULL AND parent_kind IN ('run','result')))
);
ALTER TABLE hosted_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosted_resources FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_resources_read ON hosted_resources FOR SELECT USING (
    tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid
    AND EXISTS (SELECT 1 FROM hosted_memberships m
                WHERE m.tenant_id=hosted_resources.tenant_id
                AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid)
);
CREATE POLICY tenant_resources_insert ON hosted_resources FOR INSERT WITH CHECK (
    tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid
    AND EXISTS (SELECT 1 FROM hosted_memberships m
                WHERE m.tenant_id=hosted_resources.tenant_id
                AND m.user_id=nullif(current_setting('app.user_id',true),'')::uuid
                AND m.role IN ('owner','operator'))
);
-- Runtime roles get explicit minimum grants during provisioning. Future domain
-- tables also require FORCE RLS and composite tenant/resource foreign keys.
REVOKE ALL ON hosted_users, hosted_tenants, hosted_memberships,
    hosted_login_challenges, hosted_sessions, hosted_rate_buckets, hosted_resources FROM PUBLIC;
COMMIT;
