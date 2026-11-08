# Security audit checkpoint — 2026-11-08

## Scope and verified state

Branch: `feat/db-session-bootstrap-resolver-2026-11`  
Initial audit head: `211f7589a0eb178fba1b6c269d5d96015b84f27b` (subsequent session-management commits are on the same branch).  
Pull request: #24 (open, Draft; do not merge as part of this work).

The following files and boundaries were inspected:
- FastAPI app composition and authenticated procurement host.
- Cookie session resolver, refresh/logout routes, session service and authorization primitives.
- Tenant-aware PostgreSQL transaction boundary.
- Migrations 0001–0007, including RLS bootstrap, refresh-token families and immutable security audit events.
- Session resolver, authenticated host, authorization and PostgreSQL RLS integration tests.
- OTP security specification and session lifecycle implementation notes.

## CI evidence at this head

- Main CI run 42509146818: success.
  - Ruff: all checks passed.
  - Pytest: 98 passed.
  - The workflow supplied TEST_DATABASE_URL and started PostgreSQL 16.15; PostgreSQL integration tests were executed in that ephemeral CI database.
- Frontend CI run 42509146857: success.
- Additional CI run 42509142485: success.

These are CI results only. They do not establish that staging browser tests, mobile-device tests or production rollout have occurred.

## Verified controls

- Procurement routes are mounted behind one PostgreSQL-backed session resolver; request body/header/query claims are not used to establish tenant, role or branch identity.
- Session resolver derives identity, tenant, role and active branch memberships from database records and checks the presented cookie digest against the current session row.
- Business transaction boundary revalidates session, identity, tenant, membership, role and branch membership.
- Refresh rotation locks the prior session row, issues a successor in the same family and revokes the family on token replay.
- Session cookies are configured with Secure, HttpOnly, SameSite=Strict and Path=/ requirements.
- Tenant-scoped tables are configured with FORCE ROW LEVEL SECURITY; PostgreSQL integration tests verify cross-tenant isolation and runtime-role restrictions.
- Security audit rows are append-only and tenant scoped.

## Remaining implementation and acceptance gates

1. Session management API is incomplete:
   - Current-session logout exists.
   - Internal `SessionService.revoke_all()` exists, but no HTTP logout-all endpoint is exposed.
   - Own-session inventory and selected-session revocation endpoints are not implemented.
   - Logout-all must require a fresh, purpose-bound step-up proof; do not expose it by merely accepting tenant/subject/session identifiers from a request.
   - Selected-session revocation must be limited to the authenticated subject and revalidate the current session inside the same transaction.

2. OTP sign-in is not implemented:
   - The approved design exists in `docs/AUTH_OTP_SECURITY_SPEC.md`.
   - Challenge delivery and verification provider adapters, challenge lifecycle, abuse controls and public sign-in endpoints remain absent.
   - Do not expose `SessionService.issue()` through an unauthenticated route.
   - Production must fail closed without configured provider and secret material.

3. Route/service audit is not yet exhaustive:
   - The procurement API host and its context dependency were inspected.
   - Continue checking every business service and route for tenant/branch scoping, ownership, authorization-before-mutation, idempotency and audit behavior.
   - Review runtime grants and actual role attributes in a disposable staging database, including owner, superuser and BYPASSRLS flags.

4. Staging and device acceptance remain outstanding:
   - Deploy only to a disposable staging environment after configuration review.
   - Exercise browser refresh/logout, CSRF/origin rejection, concurrent refresh/replay and service-worker update.
   - Perform real-device checks before any production activation.

## Explicit safety constraints

- No production database has been migrated or modified by this checkpoint.
- No deployment or production activation is authorized.
- PR #24 remains open and Draft; do not merge it.
- OTP public login remains disabled until implementation, independent review and staging acceptance are complete.
