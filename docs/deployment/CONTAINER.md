# Container deployment

## Prerequisites

- Docker Engine and Docker Compose plugin.
- A protected deployment environment for `.env`; never commit the real file.
- A TLS reverse proxy in front of the app. The Compose port binds only to `127.0.0.1`.

## First deployment

1. Copy `.env.example` to `.env`.
2. Replace `POSTGRES_PASSWORD` and `AUTH_RATE_LIMIT_SECRET` with independent random secrets. Use at least 32 random characters for `AUTH_RATE_LIMIT_SECRET`.
3. Ensure `DATABASE_URL` uses `postgresql+psycopg://` and matches the database name, user, and password. URL-encode reserved characters in the password.
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
- This Compose file does not configure TLS termination, automated encrypted backups, backup retention, restore rehearsal, metrics, alerting, or high availability. Those remain release blockers.
- Do not use real customer data until backup/restore, access-control review, and production security gates are complete.
- For upgrades, take and verify a database backup before running the migration profile.
