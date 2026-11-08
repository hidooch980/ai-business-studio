-- Shared tenant-scoped event, audit, outbox and idempotency infrastructure.
BEGIN;

CREATE TABLE idempotency_records (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    operation text NOT NULL CHECK (length(btrim(operation)) BETWEEN 1 AND 160),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 200),
    request_sha256 bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    state text NOT NULL CHECK (state IN ('processing', 'completed', 'failed')),
    response_status integer,
    response_body jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    UNIQUE (tenant_id, operation, idempotency_key),
    CHECK ((state = 'completed' AND response_status IS NOT NULL AND response_body IS NOT NULL)
        OR state <> 'completed')
);
CREATE INDEX idempotency_expiry_idx ON idempotency_records(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE domain_events (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    aggregate_type text NOT NULL CHECK (length(btrim(aggregate_type)) BETWEEN 1 AND 100),
    aggregate_id uuid NOT NULL,
    aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
    event_type text NOT NULL CHECK (length(btrim(event_type)) BETWEEN 1 AND 160),
    payload jsonb NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, aggregate_version),
    CHECK (octet_length(payload::text) <= 65536),
    CHECK (octet_length(metadata::text) <= 8192)
);
CREATE INDEX domain_events_tenant_time_idx ON domain_events(tenant_id, occurred_at DESC);
CREATE INDEX domain_events_aggregate_idx ON domain_events(tenant_id, aggregate_type, aggregate_id, aggregate_version);

CREATE TABLE outbox_messages (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    event_id uuid NOT NULL UNIQUE REFERENCES domain_events(id),
    destination text NOT NULL CHECK (length(btrim(destination)) BETWEEN 1 AND 160),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'processing', 'published', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    published_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbox_ready_idx ON outbox_messages(available_at, created_at) WHERE state IN ('pending', 'failed');

CREATE TABLE audit_events (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    actor_identity_id uuid REFERENCES identities(id),
    action text NOT NULL CHECK (length(btrim(action)) BETWEEN 1 AND 160),
    resource_type text NOT NULL CHECK (length(btrim(resource_type)) BETWEEN 1 AND 100),
    resource_id text,
    outcome text NOT NULL CHECK (outcome IN ('success', 'denied', 'failure')),
    request_id text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK (octet_length(details::text) <= 8192)
);
CREATE INDEX audit_events_tenant_time_idx ON audit_events(tenant_id, occurred_at DESC);
CREATE INDEX audit_events_resource_idx ON audit_events(tenant_id, resource_type, resource_id, occurred_at DESC);

DO $migration$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['idempotency_records', 'domain_events', 'outbox_messages', 'audit_events'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'', true), '''')::uuid)',
            table_name
        );
    END LOOP;
END
$migration$;

CREATE FUNCTION reject_immutable_record_mutation() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    RAISE EXCEPTION 'table % is append-only; use a compensating record', TG_TABLE_NAME;
END
$function$;

CREATE TRIGGER domain_events_append_only
BEFORE UPDATE OR DELETE ON domain_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

COMMIT;
