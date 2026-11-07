# Container deployment

## Prerequisites

- Docker Engine and Docker Compose plugin.
- A protected deployment environment for `.env`; never commit the real file.
- Separate `abs_app` and `abs_migrator` credentials; the container entrypoint creates both as non-superuser roles.
- A TLS reverse proxy in front of the app. The Compose port binds only to `127.0.0.1`.

## First deployment

1. Copy `.env.example` to `.env`.
2. Replace `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `MIGRATOR_DB_PASSWORD`, and `AUTH_RATE_LIMIT_SECRET` with independent random secrets. Use at least 32 random characters for `AUTH_RATE_LIMIT_SECRET`. Use at least 32 random characters for `AUTH_RATE_LIMIT_SECRET`.
3. Set `DATABASE_URL` to the `abs_app` role and `MIGRATION_DATABASE_URL` to the `abs_migrator` role. Both must use `postgresql+psycopg://` and match the database name and passwords. URL-encode reserved characters in passwords.
4. Build and apply the reviewed schema migration:

   ```bash
   docker compose --profile migrate run --rm migrate
   ```

5. Start the API:

   ```bash
   docker compose up -d app
   ```

6. Verify the health endpoint locally and through the TLS reverse proxy:

   ```bash
   curl --fail http://127.0.0.1:8000/api/v1/health
   ```

## Operational cautions

- Public registration remains disabled.
- The API image runs as an unprivileged UID and has a read-only root filesystem.
- PostgreSQL data is stored in a named Docker volume.
- Encrypted PostgreSQL backup and guarded restore scripts are provided in [backup/restore operations](BACKUP_RESTORE.md); scheduled execution, off-host storage, alerting, and a verified restore rehearsal remain release blockers.
- This Compose file does not configure TLS termination, metrics, alerting, or high availability. Those remain release blockers.
- Do not use real customer data until backup/restore, access-control review, and production security gates are complete.
- For upgrades, take and verify a database backup before running the migration profile.
