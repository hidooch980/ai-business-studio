from pathlib import Path

MIGRATION = Path("migrations/0001_identity_security.sql")


def test_identity_security_migration_has_required_tables_and_constraints():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for table in (
        "tenants",
        "branches",
        "identities",
        "tenant_memberships",
        "branch_memberships",
        "auth_sessions",
        "otp_challenges",
        "security_audit_events",
    ):
        assert f"create table {table}" in sql
    assert "refresh_token_hash bytea not null unique" in sql
    assert "code_hmac bytea not null" in sql
    assert "failed_attempts between 0 and 5" in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "with check" in sql
    assert "current_setting('app.tenant_id', true)" in sql


def test_migration_never_persists_plaintext_otp_or_refresh_tokens():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "otp_code text" not in sql
    assert "refresh_token text" not in sql
    assert "code_hmac bytea" in sql
    assert "refresh_token_hash bytea" in sql
