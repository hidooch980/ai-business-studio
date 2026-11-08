BEGIN;

GRANT CREATE ON SCHEMA public TO auth_session_lookup_owner;

-- CSRF tokens are bound to the server-side session and never accepted from
-- request payloads. Existing sessions without a hash cannot perform writes.
ALTER TABLE public.auth_sessions
    ADD COLUMN csrf_token_hash bytea;
ALTER TABLE public.auth_sessions
    ADD CONSTRAINT auth_sessions_csrf_hash_length
    CHECK (csrf_token_hash IS NULL OR octet_length(csrf_token_hash) = 32);

-- The non-login SECURITY DEFINER owner receives only the minimum columns
-- needed to issue and consume OTP challenges. It remains NOBYPASSRLS.
GRANT SELECT (id, phone_e164, email, is_active)
    ON public.identities TO auth_session_lookup_owner;
CREATE POLICY auth_session_lookup_owner_identity_read
    ON public.identities FOR SELECT TO auth_session_lookup_owner USING (true);

GRANT SELECT, INSERT, UPDATE
    ON public.otp_challenges TO auth_session_lookup_owner;
CREATE POLICY auth_session_lookup_owner_otp_access
    ON public.otp_challenges FOR ALL TO auth_session_lookup_owner
    USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION public.issue_auth_otp(
    p_challenge_id uuid,
    p_identifier text,
    p_identifier_fingerprint bytea,
    p_code_hmac bytea,
    p_channel text
)
RETURNS text
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    matched_identity_id uuid;
    destination text;
BEGIN
    IF p_challenge_id IS NULL
       OR p_identifier_fingerprint IS NULL
       OR octet_length(p_identifier_fingerprint) <> 32
       OR p_code_hmac IS NULL
       OR octet_length(p_code_hmac) <> 32
       OR p_channel NOT IN ('sms', 'email')
       OR length(p_identifier) > 254 THEN
        RAISE EXCEPTION 'invalid OTP request' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(encode(p_identifier_fingerprint, 'hex'), 0)
    );

    IF (
        SELECT count(*) FROM public.otp_challenges
        WHERE identifier_fingerprint = p_identifier_fingerprint
          AND created_at > clock_timestamp() - interval '1 hour'
    ) >= 5 OR EXISTS (
        SELECT 1 FROM public.otp_challenges
        WHERE identifier_fingerprint = p_identifier_fingerprint
          AND created_at > clock_timestamp() - interval '60 seconds'
    ) THEN
        RETURN NULL;
    END IF;

    IF p_channel = 'sms' THEN
        SELECT i.id, i.phone_e164 INTO matched_identity_id, destination
        FROM public.identities AS i
        WHERE i.phone_e164 = p_identifier AND i.is_active
        LIMIT 1;
    ELSE
        SELECT i.id, i.email INTO matched_identity_id, destination
        FROM public.identities AS i
        WHERE lower(i.email) = lower(p_identifier) AND i.is_active
        LIMIT 1;
    END IF;

    UPDATE public.otp_challenges
       SET invalidated_at = clock_timestamp()
     WHERE identifier_fingerprint = p_identifier_fingerprint
       AND consumed_at IS NULL AND invalidated_at IS NULL;

    INSERT INTO public.otp_challenges (
        id, identity_id, identifier_fingerprint, code_hmac,
        purpose, channel, expires_at, resend_after
    ) VALUES (
        p_challenge_id,
        matched_identity_id,
        p_identifier_fingerprint, p_code_hmac, 'login', p_channel,
        clock_timestamp() + interval '5 minutes',
        clock_timestamp() + interval '60 seconds'
    );

    RETURN destination;
END
$function$;

CREATE OR REPLACE FUNCTION public.consume_auth_otp(
    p_challenge_id uuid,
    p_identifier_fingerprint bytea,
    p_code_hmac bytea
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    challenge public.otp_challenges%ROWTYPE;
BEGIN
    SELECT c.* INTO challenge
    FROM public.otp_challenges AS c
    WHERE c.id = p_challenge_id
      AND c.identifier_fingerprint = p_identifier_fingerprint
    FOR UPDATE;

    IF NOT FOUND OR challenge.consumed_at IS NOT NULL
       OR challenge.invalidated_at IS NOT NULL
       OR challenge.expires_at <= clock_timestamp()
       OR challenge.failed_attempts >= 5 THEN
        RETURN NULL;
    END IF;

    IF challenge.code_hmac <> p_code_hmac THEN
        UPDATE public.otp_challenges
           SET failed_attempts = failed_attempts + 1
         WHERE id = p_challenge_id;
        RETURN NULL;
    END IF;

    UPDATE public.otp_challenges
       SET consumed_at = clock_timestamp()
     WHERE id = p_challenge_id;

    RETURN challenge.identity_id;
END
$function$;

ALTER FUNCTION public.issue_auth_otp(uuid, text, bytea, bytea, text)
    OWNER TO auth_session_lookup_owner;
ALTER FUNCTION public.consume_auth_otp(uuid, bytea, bytea)
    OWNER TO auth_session_lookup_owner;

REVOKE ALL ON FUNCTION public.issue_auth_otp(uuid, text, bytea, bytea, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.consume_auth_otp(uuid, bytea, bytea) FROM PUBLIC;

DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_runtime') THEN
        GRANT EXECUTE ON FUNCTION public.issue_auth_otp(uuid, text, bytea, bytea, text)
            TO retail_runtime;
        GRANT EXECUTE ON FUNCTION public.consume_auth_otp(uuid, bytea, bytea)
            TO retail_runtime;
        GRANT INSERT, UPDATE ON public.auth_sessions TO retail_runtime;
        GRANT SELECT (id, tenant_id, identity_id, expires_at, revoked_at, csrf_token_hash)
            ON public.auth_sessions TO retail_runtime;
    END IF;
END
$grant$;


GRANT SELECT (csrf_token_hash)
    ON public.auth_sessions TO auth_session_lookup_owner;

-- Replace the initial resolver with a narrowly-scoped variant that also
-- returns the stored CSRF digest. Runtime still cannot SELECT auth_sessions.
CREATE FUNCTION public.resolve_auth_session_with_csrf(p_token_sha256 bytea)
RETURNS TABLE (
    session_id uuid,
    tenant_id uuid,
    identity_id uuid,
    csrf_token_hash bytea
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

    SELECT s.id, s.tenant_id, s.identity_id, s.expires_at,
           s.revoked_at, s.csrf_token_hash
      INTO matched_session
    FROM public.auth_sessions AS s
    WHERE s.refresh_token_hash = p_token_sha256
    LIMIT 1;

    IF NOT FOUND THEN
        INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
        VALUES (NULL, 'unknown');
        RETURN;
    END IF;

    IF matched_session.revoked_at IS NOT NULL THEN
        INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
        VALUES (matched_session.id, 'revoked');
        RETURN;
    END IF;

    IF matched_session.expires_at <= clock_timestamp() THEN
        INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
        VALUES (matched_session.id, 'expired');
        RETURN;
    END IF;

    INSERT INTO public.auth_session_lookup_audit (session_id, outcome)
    VALUES (matched_session.id, 'matched');

    RETURN QUERY
    SELECT matched_session.id, matched_session.tenant_id,
           matched_session.identity_id, matched_session.csrf_token_hash;
END
$function$;

ALTER FUNCTION public.resolve_auth_session_with_csrf(bytea) OWNER TO auth_session_lookup_owner;
REVOKE ALL ON FUNCTION public.resolve_auth_session_with_csrf(bytea) FROM PUBLIC;

DO $resolver_grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_runtime') THEN
        GRANT EXECUTE ON FUNCTION public.resolve_auth_session_with_csrf(bytea) TO retail_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_session_runtime') THEN
        GRANT EXECUTE ON FUNCTION public.resolve_auth_session_with_csrf(bytea) TO retail_session_runtime;
    END IF;
END
$resolver_grant$;

REVOKE CREATE ON SCHEMA public FROM auth_session_lookup_owner;

COMMIT;
