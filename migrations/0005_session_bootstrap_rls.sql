-- Narrow session bootstrap lookup for the runtime role.
-- Pre-provision auth_bootstrap_owner as NOLOGIN NOBYPASSRLS. Never grant it BYPASSRLS.
-- The bootstrap table contains only a token digest and the identifiers needed to
-- establish the normal RLS context. Runtime users get EXECUTE, never table access.
BEGIN;

CREATE TABLE auth_session_bootstrap (
    token_hash bytea PRIMARY KEY,
    session_id uuid NOT NULL UNIQUE,
    tenant_id uuid NOT NULL,
    identity_id uuid NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
REVOKE ALL ON auth_session_bootstrap FROM PUBLIC;
ALTER TABLE auth_session_bootstrap OWNER TO auth_bootstrap_owner;

CREATE FUNCTION sync_auth_session_bootstrap()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        DELETE FROM public.auth_session_bootstrap WHERE session_id = OLD.id;
        RETURN OLD;
    END IF;

    INSERT INTO public.auth_session_bootstrap
        (token_hash, session_id, tenant_id, identity_id, expires_at, revoked_at)
    VALUES
        (NEW.refresh_token_hash, NEW.id, NEW.tenant_id, NEW.identity_id, NEW.expires_at, NEW.revoked_at)
    ON CONFLICT (session_id) DO UPDATE SET
        token_hash = EXCLUDED.token_hash,
        tenant_id = EXCLUDED.tenant_id,
        identity_id = EXCLUDED.identity_id,
        expires_at = EXCLUDED.expires_at,
        revoked_at = EXCLUDED.revoked_at;

    RETURN NEW;
END
$fn$;
ALTER FUNCTION sync_auth_session_bootstrap() OWNER TO auth_bootstrap_owner;
REVOKE ALL ON FUNCTION sync_auth_session_bootstrap() FROM PUBLIC;

CREATE TRIGGER auth_sessions_bootstrap_sync
AFTER INSERT OR UPDATE OF refresh_token_hash, tenant_id, identity_id, expires_at, revoked_at OR DELETE
ON auth_sessions
FOR EACH ROW EXECUTE FUNCTION sync_auth_session_bootstrap();

CREATE FUNCTION resolve_auth_session_bootstrap(p_token_hash bytea)
RETURNS TABLE (tenant_id uuid, identity_id uuid, session_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $fn$
    SELECT b.tenant_id, b.identity_id, b.session_id
    FROM public.auth_session_bootstrap AS b
    WHERE b.token_hash = p_token_hash
      AND b.revoked_at IS NULL
      AND b.expires_at > statement_timestamp()
    LIMIT 1
$fn$;
ALTER FUNCTION resolve_auth_session_bootstrap(bytea) OWNER TO auth_bootstrap_owner;
REVOKE ALL ON FUNCTION resolve_auth_session_bootstrap(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_auth_session_bootstrap(bytea) TO app_runtime;

COMMIT;
