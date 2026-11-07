# Quality and Release Gates

This document defines the minimum evidence required before a change can be merged or a release can be published.

## Pull request gates

- [ ] Ruff lint passes.
- [ ] Pytest passes on every supported Python version.
- [ ] New behavior has regression tests; bug fixes include a test reproducing the defect.
- [ ] Dependency changes are reviewed for maintenance status, license, and known vulnerabilities.
- [ ] No secrets, personal data, production exports, database files, signing material, or private certificates are present.
- [ ] API and database changes include compatibility and migration notes.
- [ ] Tenant-scoped reads and writes are tested for cross-tenant isolation once tenancy exists.
- [ ] Financial calculations use Decimal and explicit currency/rounding rules.
- [ ] Offline-critical operations do not require external network access.

## Database gates

- Migrations must be forward-testable from an empty database and from the previous supported schema.
- Destructive migrations require a documented backup and rollback/recovery plan.
- PostgreSQL integration tests must run against PostgreSQL, not only SQLite.
- Concurrent writes, uniqueness constraints, transaction rollback, and idempotency must be tested.
- Backup restoration must be exercised in CI or a documented release rehearsal.

## Security gates

- CI permissions follow least privilege.
- Third-party GitHub Actions are reviewed and pinned to immutable commit SHAs before production release.
- Dependency vulnerability scanning and secret scanning must be enabled.
- Authentication, authorization, tenant isolation, rate limiting, and audit events require negative tests.
- Production credentials and signing keys are supplied only through protected secret storage.
- Webhooks require signature verification, replay protection, and idempotent processing.

## Release gates

A release is blocked if any required test is failing, any high-severity unresolved security finding exists, migrations are unverified, or the artifact cannot be installed and upgraded on supported platforms.

A green foundation CI run is not evidence that unimplemented product modules are production-ready.
