import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_and_downgrade_on_sqlite(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "alembic_version",
            "tenants",
            "users",
            "memberships",
            "roles",
            "permissions",
            "role_permissions",
            "membership_roles",
            "user_sessions",
            "audit_events",
        }.issubset(tables)
    finally:
        engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == set()
    finally:
        engine.dispose()
