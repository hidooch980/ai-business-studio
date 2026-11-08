BEGIN;

-- This non-login role is deliberately privileged only for one table and one
-- SECURITY DEFINER function. It has BYPASSRLS so it can locate a session before
-- tenant/subject context exists, but receives no privileges on other tables.
DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auth_session_lookup_owner') THEN
        CREATE ROLE auth_session_lookup_owner NOLOGIN BYPASSRLS;
    END IF;
END
$role$;

GRANT USAGE ON SCHEMA public TO auth_session_lookup_owner;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM auth_session_lookup_owner;
GRANT CREATE ON SCHEMA public TO auth_session_lookup_owner;
GRANT SELECT (id, tenant_id, identity_id, refresh_token_hash, expires_at, revoked_at)
    ON TABLE public.auth_sessions TO auth_session_lookup_owner;

CREATE TABLE public.auth_session_lookup_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    session_id uuid,
    outcome text NOT NULL CHECK (outcome IN ('matched', 'unknown'))
);
ALTER TABLE public.auth_session_lookup_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_session_lookup_audit FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.auth_session_lookup_audit FROM PUBLIC;

GRANT INSERT ON TABLE public.auth_session_lookup_audit TO auth_session_lookup_owner;
GRANT USAGE ON SEQUENCE public.auth_session_lookup_audit_id_seq TO auth_session_lookup_owner;

CREATE OR REPLACE FUNCTION public.resolve_auth_session(p_token_sha256 bytea)
RETURNS TABLE (
    session_id uuid,
    tenant_id uuid,
    identity_id uuid,
    expires_at timestamptz,
    revoked_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    matched_session record;
BEGIN
    IF p_token_sha256 IS NULL OR octet_length(p_token_sha256) <> 32 THEN
        INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
        VALUES (NULL, 'unknown');
        RETURN;
    END IF;

    SELECT s.id, s.tenant_id, s.identity_id, s.expires_at, s.revoked_at
      INTO matched_session
    FROM public.auth_sessions AS s
    WHERE s.refresh_token_hash = p_token_sha256
    LIMIT 1;

    IF NOT FOUND THEN
        INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
        VALUES (NULL, 'unknown');
        RETURN;
    END IF;

    INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
    VALUES (matched_session.id, 'matched');

    RETURN QUERY
    SELECT matched_session.id, matched_session.tenant_id,
           matched_session.identity_id, matched_session.expires_at,
           matched_session.revoked_at;
END
$function$;

ALTER FUNCTION public.resolve_auth_session(bytea) OWNER TO auth_session_lookup_owner;
REVOKE CREATE ON SCHEMA public FROM auth_session_lookup_owner;
REVOKE ALL ON FUNCTION public.resolve_auth_session(bytea) FROM PUBLIC;

-- Runtime role is provisioned by deployment before migrations are applied.
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_runtime') THEN
        GRANT EXECUTE ON FUNCTION public.resolve_auth_session(bytea) TO retail_runtime;
        REVOKE SELECT ON TABLE public.auth_sessions FROM retail_runtime;
    END IF;
END
$grant$;

COMMIT;
