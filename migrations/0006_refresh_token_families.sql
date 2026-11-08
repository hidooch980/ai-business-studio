-- Add refresh-token family tracking and permit a presented token digest to
-- resolve its own row even after rotation, so reuse can revoke the whole family.
BEGIN;

ALTER TABLE auth_sessions
    ADD COLUMN token_family_id uuid;

UPDATE auth_sessions
SET token_family_id = id
WHERE token_family_id IS NULL;

ALTER TABLE auth_sessions
    ALTER COLUMN token_family_id SET NOT NULL;

ALTER TABLE auth_sessions ALTER COLUMN token_family_id SET DEFAULT gen_random_uuid();

CREATE INDEX auth_sessions_family_idx
    ON auth_sessions(token_family_id);

CREATE INDEX auth_sessions_rotated_from_idx
    ON auth_sessions(rotated_from_session_id)
    WHERE rotated_from_session_id IS NOT NULL;

CREATE OR REPLACE FUNCTION resolve_auth_session_bootstrap(p_token_hash bytea)
RETURNS TABLE (tenant_id uuid, identity_id uuid, session_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $fn$
    SELECT b.tenant_id, b.identity_id, b.session_id
    FROM public.auth_session_bootstrap AS b
    WHERE b.token_hash = p_token_hash
    LIMIT 1
$fn$;

ALTER FUNCTION resolve_auth_session_bootstrap(bytea) OWNER TO auth_bootstrap_owner;
REVOKE ALL ON FUNCTION resolve_auth_session_bootstrap(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_auth_session_bootstrap(bytea) TO retail_runtime;

COMMIT;
