# Security Policy

## Scope

This policy applies to the AI Business Studio source repository and its supported releases.

## Reporting a vulnerability

Do not disclose exploitable vulnerabilities in public issues. Contact the repository owner privately through GitHub's security reporting mechanism, if enabled, or request a private contact channel.

Include the affected component, impact, reproduction steps, and a proposed mitigation where possible. Do not include real customer records, payment credentials, or secrets in a report.

## Security requirements

- Never commit API tokens, passwords, signing keys, private certificates, production .env files, database files, backups, or logs.
- Treat any previously exposed private signing key as compromised; rotate it before production use.
- Keep signing private keys in protected CI secrets or an approved secret manager. Pin only the corresponding public verification key in clients.
- Never store CVV, PIN, magnetic-stripe track data, or full payment-card numbers.
- Enforce tenant isolation and authorization on the server side.
- Record sensitive administrative and financial actions in tamper-evident audit trails.
- Require human authorization for money movement and other high-impact operations.
- Validate webhook signatures and prevent replay and duplicate processing.
- Test backup restoration, not only backup creation.

## Disclosure

Coordinate remediation and release timing with the repository owner before public disclosure.
