import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_and_downgrade_on_sqlite(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, f"alembic upgrade failed:\\n{upgrade.stdout}\\n{upgrade.stderr}"
    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "csrf_token_hash" in {column["name"] for column in inspect(engine).get_columns("user_sessions")}
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
            "login_rate_limits",
        }.issubset(tables)
    finally:
        engine.dispose()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, f"alembic downgrade failed:\\n{downgrade.stdout}\\n{downgrade.stderr}"
    engine = create_engine(database_url)
    try:
        assert not (tables - {"alembic_version"}).intersection(inspect(engine).get_table_names())
    finally:
        engine.dispose()
