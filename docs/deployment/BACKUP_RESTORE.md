# Encrypted PostgreSQL backup and restore

These scripts provide encrypted custom-format PostgreSQL dumps. They do not, by themselves, constitute a tested disaster-recovery program.

## Prerequisites

Install PostgreSQL client utilities and [age](https://age-encryption.org/). Use a dedicated backup identity and a separately stored age private identity. Never place private keys or database passwords in the repository.

Configure libpq service definitions outside the repository (for example, in a mode-0600 `~/.pg_service.conf`) and a mode-0600 `PGPASSFILE`. Set `PGSERVICE`, `PGDATABASE`, and `PGPASSFILE` in the protected job environment. The service definition should point to the intended PostgreSQL host and port.

Generate an age recipient/identity pair and store the recipient in `BACKUP_AGE_RECIPIENT`; keep the private identity offline or in a separate secrets manager. Do not store both with the backup.

## Create an encrypted backup

```bash
export PGSERVICE=ai-business-studio-backup
export PGDATABASE=ai_business_studio
export PGPASSFILE=/etc/ai-business-studio/backup.pgpass
export BACKUP_DIR=/var/backups/ai-business-studio
export BACKUP_AGE_RECIPIENT='age1...'
export BACKUP_RETENTION_DAYS=30
./scripts/backup-postgres.sh
```

The script uses `pg_dump` custom format, encrypts the dump before publishing it, sets restrictive file permissions, and writes a SHA-256 checksum for the encrypted artifact. Store a second copy off-host with restricted access.

A hardened systemd service and persistent daily timer template are provided under `deploy/systemd/`. To install:

1. Install PostgreSQL client tools and `age`; create a dedicated `abs-backup` system user.
2. Install the scripts under `/opt/ai-business-studio/scripts/` and create `/var/backups/ai-business-studio` owned by `abs-backup` with mode 0700.
3. Create `/etc/ai-business-studio/backup.env` (mode 0600, owned by `abs-backup`) with `PGSERVICE`, `PGSERVICEFILE`, `PGDATABASE`, `PGPASSFILE`, `BACKUP_DIR`, `BACKUP_AGE_RECIPIENT`, and `BACKUP_RETENTION_DAYS`. Keep the password file and service definition protected and outside this repository.
4. Install both unit files under `/etc/systemd/system/`, run `systemctl daemon-reload`, then `systemctl enable --now ai-business-studio-backup.timer`.
5. Verify with `systemctl list-timers` and run `systemctl start ai-business-studio-backup.service` once as a controlled test.

Configure monitoring for missed backups and disk capacity; a scheduled command without alerting is not reliable backup coverage.

## Restore (destructive)

1. Provision a separate, empty recovery database and verify the configured libpq service points to that database.
2. Keep the `.sha256` sidecar beside the encrypted artifact; the restore utility verifies it before decryption.
3. Make the age private identity available through a protected path.
4. Run the restore only after confirming the target database name and host:

```bash
export PGSERVICE=ai-business-studio-recovery
export PGDATABASE=ai_business_studio_recovery
export PGPASSFILE=/etc/ai-business-studio/recovery.pgpass
export BACKUP_FILE=/var/backups/ai-business-studio/ai_business_studio-YYYYMMDDTHHMMSSZ.dump.age
export AGE_IDENTITY_FILE=/secure/offline/ai-business-studio-age-identity.txt
export RESTORE_CONFIRMATION=I_HAVE_VERIFIED_THE_TARGET_DATABASE
./scripts/restore-postgres.sh
```

The restore script verifies the SHA-256 sidecar before decrypting, refuses to run without the exact confirmation phrase, restricts the target database name, and invokes `pg_restore --single-transaction --clean --if-exists`. It can replace objects in the target database, but a failed restore is rolled back as one transaction. Never point it at the live production database for a rehearsal.

## Release gate still required

- Run a scheduled backup on the actual staging deployment.
- Restore into an isolated database on a separate host.
- Verify schema revision, tenant counts, ledger totals, inventory balances, and application health.
- Record measured RPO/RTO, retention, off-host copy, key recovery, and an operator sign-off.
- Add monitoring/alerting and rehearse key rotation.

Until this rehearsal is recorded, backup/restore remains a production release blocker.
