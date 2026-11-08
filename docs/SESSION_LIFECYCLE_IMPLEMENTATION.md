# Session lifecycle implementation status

## Implemented in this branch
- `SessionService.issue()` creates an opaque 384-bit URL-safe refresh credential after a trusted caller has completed identity verification and the service rechecks active identity, tenant and membership.
- Only SHA-256 token digests are persisted; plaintext refresh tokens are returned once to the caller.
- `SessionService.rotate()` locks the presented session row with `FOR UPDATE`, consumes it once, and creates a successor in the same token family.
- Reuse of a consumed token revokes all active sessions in that token family. The row lock serializes concurrent refresh attempts.
- `SessionService.revoke()` and the HTTP logout endpoint revoke the presented session.
- `POST /api/v1/auth/refresh` rotates the secure `__Host-retail_session` cookie.
- `POST /api/v1/auth/logout` revokes the current cookie session and clears the cookie.
- Refresh/logout require a matching Origin and reject cross-site Fetch Metadata.
- Migration `0006_refresh_token_families.sql` adds family tracking and preserves existing sessions by assigning each a family ID.
- Migration `0007_security_audit_immutability.sql` makes session security audit records append-only and restricts reads to tenant owner/admin identities.
- Session issue, successful rotation, replay, expiry/authorization denial, current-session logout and logout-all operations write security audit events in the same database transaction.
- PostgreSQL integration tests cover issuance, rotation, replay, concurrent refresh, logout and membership revocation.

## Authentication entrypoint deliberately not exposed yet
The approved product security design specifies phone/email OTP as the primary sign-in proof. The OTP challenge verification and delivery provider are not implemented in this branch, and no fixed-code or unauthenticated identity-to-session endpoint is provided. `SessionService.issue()` is an internal post-verification operation only. A public login endpoint must be added together with the approved OTP verification flow and provider/rate-limit controls; otherwise it would create an authentication bypass.

## Deployment and rollout
- Apply migrations only to a disposable/test database during CI. Migration `0006` is not run against production by this change.
- Runtime role must remain non-owner, non-superuser and `NOBYPASSRLS`.
- Serve the web app over HTTPS so `Secure` and `__Host-` cookie semantics are enforced.
- Reverse proxies must pass a trusted HTTPS scheme/host to FastAPI; do not trust arbitrary forwarded headers.
- Set the frontend/backend same-origin deployment so Origin validation succeeds.
- Do not enable production sign-in until OTP verification, abuse controls, CSRF/origin policy, key management, audit alerts and operational rollback are reviewed.

## Remaining acceptance gates
1. Implement OTP verification and only then expose login/session issuance over HTTP.
2. Add logout-all HTTP route and session inventory/revocation UI; the internal revoke-all service primitive exists.
3. Run PostgreSQL 16 CI and verify all concurrency tests pass.
4. Deploy to a disposable staging environment and perform browser-level refresh/logout and service-worker update tests.
5. Conduct independent security review before production activation.
