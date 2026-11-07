import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import build_engine


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL CI service is not configured")
def test_postgresql_migrations_and_append_only_audit_trigger() -> None:
    environment = os.environ.copy()
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, f"PostgreSQL migration failed:\\n{upgrade.stdout}\\n{upgrade.stderr}"

    engine = build_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                    (id, tenant_id, actor_user_id, action, resource_type, resource_id, outcome, request_id, created_at)
                    VALUES (CAST(:id AS uuid), NULL, NULL, 'test.created', 'test', '1', 'success', NULL, :created_at)
                    """
                ),
                {"id": str(uuid4()), "created_at": "2026-01-01T00:00:00+00:00"},
            )
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("UPDATE audit_events SET outcome = 'tampered'"))
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM audit_events"))
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE TABLE audit_events"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 1
    finally:
        engine.dispose()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, f"PostgreSQL downgrade failed:\\n{downgrade.stdout}\\n{downgrade.stderr}"
