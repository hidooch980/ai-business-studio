"""Ordered PostgreSQL SQL migration runner with a session advisory lock."""
from __future__ import annotations

from pathlib import Path
import re

MIGRATION_LOCK_ID = 7_341_102_026


def apply_migrations(database_url: str, migrations_dir: str | Path) -> list[str]:
    """Apply unapplied numbered SQL migrations in order; intended for deployment tooling.

    Run with a schema-owner connection, not the restricted application runtime role.
    The runner is for a fresh or already-ledgered database; legacy manually-applied
    migrations must be baselined explicitly before invoking it.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("install psycopg[binary] to run PostgreSQL migrations") from exc

    directory = Path(migrations_dir)
    scripts = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not scripts:
        raise ValueError(f"no numbered SQL migrations found in {directory}")

    applied: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            for script in scripts:
                version = script.name
                exists = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                ).fetchone()
                if exists:
                    continue
                sql = script.read_text(encoding="utf-8")
                # SQL files are also directly executable and therefore carry
                # BEGIN/COMMIT. Strip those wrappers so the migration and its
                # ledger entry commit atomically in this runner.
                sql = re.sub(r"^\\s*BEGIN\\s*;", "", sql, count=1, flags=re.IGNORECASE)
                sql = re.sub(r"\\s*COMMIT\\s*;\\s*$", "", sql, count=1, flags=re.IGNORECASE)
                with connection.transaction():
                    connection.execute(sql, prepare=False)
                    connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES (%s)",
                        (version,),
                    )
                applied.append(version)
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
    return applied
