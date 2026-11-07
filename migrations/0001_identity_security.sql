-- Identity, tenant membership, branch membership, sessions, OTP challenges and audit.
-- Apply with a migration runner as the schema owner. Runtime DB role must NOT own
-- these tables and must not have SUPERUSER or BYPASSRLS.
BEGIN;

CREATE TABLE tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'closed')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE branches (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE identities (
    id uuid PRIMARY KEY,
    account_type text NOT NULL CHECK (account_type IN ('workforce', 'customer')),
    phone_e164 text,
    email text,
    display_name text NOT NULL DEFAULT '',
    is_active boolean NOT NULL DEFAULT true,
    phone_verified_at timestamptz,
    email_verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (phone_e164 IS NOT NULL OR email IS NOT NULL),
    CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\\+[1-9][0-9]{7,14}$')
);
CREATE UNIQUE INDEX identities_phone_e164_uq ON identities(phone_e164) WHERE phone_e164 IS NOT NULL;
CREATE UNIQUE INDEX identities_email_lower_uq ON identities(lower(email)) WHERE email IS NOT NULL;

CREATE TABLE tenant_memberships (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    identity_id uuid NOT NULL REFERENCES identities(id),
    role text NOT NULL CHECK (role IN ('owner_admin', 'branch_manager', 'employee', 'customer')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('invited', 'active', 'suspended', 'revoked')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, identity_id),
);
CREATE INDEX tenant_memberships_identity_idx ON tenant_memberships(identity_id, status);

CREATE TABLE branch_memberships (
    tenant_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    identity_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, branch_id, identity_id),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches(tenant_id, id),
    FOREIGN KEY (tenant_id, identity_id) REFERENCES tenant_memberships(tenant_id, identity_id)
);
CREATE INDEX branch_memberships_identity_idx ON branch_memberships(tenant_id, identity_id, status);

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    identity_id uuid NOT NULL,
    refresh_token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    rotated_from_session_id uuid REFERENCES auth_sessions(id),
    device_label text,
    ip_prefix inet,
    CHECK (expires_at > created_at),
    FOREIGN KEY (tenant_id, identity_id) REFERENCES tenant_memberships(tenant_id, identity_id)
);
CREATE INDEX auth_sessions_subject_idx ON auth_sessions(tenant_id, identity_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE otp_challenges (
    id uuid PRIMARY KEY,
    tenant_id uuid REFERENCES tenants(id),
    identity_id uuid REFERENCES identities(id),
    identifier_fingerprint bytea NOT NULL,
    code_hmac bytea NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('login', 'identifier_verify', 'recovery', 'step_up')),
    channel text NOT NULL CHECK (channel IN ('sms', 'email')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    invalidated_at timestamptz,
    failed_attempts smallint NOT NULL DEFAULT 0 CHECK (failed_attempts BETWEEN 0 AND 5),
    resend_after timestamptz NOT NULL,
    CHECK (expires_at > created_at),
    CHECK (resend_after >= created_at)
);
CREATE INDEX otp_challenges_fingerprint_idx ON otp_challenges(identifier_fingerprint, created_at DESC);
CREATE INDEX otp_challenges_active_idx ON otp_challenges(expires_at)
    WHERE consumed_at IS NULL AND invalidated_at IS NULL;

CREATE TABLE security_audit_events (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    actor_identity_id uuid REFERENCES identities(id),
    event_type text NOT NULL CHECK (length(btrim(event_type)) BETWEEN 1 AND 120),
    outcome text NOT NULL CHECK (outcome IN ('success', 'denied', 'failure')),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    request_id text,
    subject_identity_id uuid REFERENCES identities(id),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (octet_length(metadata::text) <= 8192)
);
CREATE INDEX security_audit_tenant_time_idx ON security_audit_events(tenant_id, occurred_at DESC);
CREATE INDEX security_audit_actor_time_idx ON security_audit_events(tenant_id, actor_identity_id, occurred_at DESC);

-- The API must set these transaction-locally after validating the session and
-- resolving active membership from trusted database records:
-- SET LOCAL app.tenant_id = '<uuid>';
-- SET LOCAL app.subject_id = '<uuid>';
-- Missing settings intentionally match no rows.
DO $migration$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'branches', 'tenant_memberships', 'branch_memberships',
        'auth_sessions', 'otp_challenges', 'security_audit_events'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid)',
            table_name
        );
    END LOOP;
END
$migration$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_self_scope ON tenants
USING (id = nullif(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- Identities are visible only when they are the current subject or share the
-- current tenant through a membership. The policy remains deny-by-default.
ALTER TABLE identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE identities FORCE ROW LEVEL SECURITY;
CREATE POLICY identity_self_or_tenant ON identities
USING (
    id = nullif(current_setting('app.subject_id', true), '')::uuid
    OR EXISTS (
        SELECT 1 FROM tenant_memberships tm
        WHERE tm.identity_id = identities.id
          AND tm.tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    )
)
WITH CHECK (
    id = nullif(current_setting('app.subject_id', true), '')::uuid
);

-- Sessions are private to their subject, even within the same tenant.
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY tenant_isolation ON auth_sessions;
CREATE POLICY session_subject_scope ON auth_sessions
USING (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    AND identity_id = nullif(current_setting('app.subject_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    AND identity_id = nullif(current_setting('app.subject_id', true), '')::uuid
);

COMMIT;
