# Security Policy

## Supported status

This repository is under active development. The current branch and pull request are not a production release. Authentication, OTP delivery, session lifecycle hardening and deployment controls are not yet complete.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, personal data or production information. Contact the repository owner privately through the GitHub account that maintains this repository. Include:
- A concise impact description and affected commit/branch.
- Reproduction steps in a disposable test environment.
- Relevant logs with tokens, credentials and personal data removed.
- A suggested mitigation, if known.

Do not test against production systems or data without explicit authorization.

## Secret handling

Never commit database URLs, API tokens, OTP values, provider credentials, private keys, signing keys, customer records, payment-card data, backups or environment files. Rotate any secret that may have been exposed.

## Release security gates

A release must not be called production-ready until:
- OTP sign-in and provider abuse controls are implemented and reviewed.
- Session rotation, revocation, idle/absolute expiry and security audit trails are tested.
- PostgreSQL RLS and tenant/branch isolation tests pass using a least-privilege runtime role.
- Browser security headers, HTTPS/proxy configuration and CSRF/origin protections are verified.
- Dependency versions are locked and vulnerability scanning is reviewed.
- Staging and backup/restore tests pass.
- No unresolved critical or high severity security findings remain.
