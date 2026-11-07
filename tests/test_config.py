import pytest

from backend.app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_requires_postgresql_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "s" * 48)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///production.db")
    with pytest.raises(ValueError, match="PostgreSQL"):
        get_settings()


def test_production_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "s" * 48)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="PostgreSQL"):
        get_settings()


def test_production_requires_secure_session_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "s" * 48)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:secret@localhost/app")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        get_settings()


def test_valid_production_configuration_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "unique-production-secret-" + "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:secret@localhost/app")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    settings = get_settings()
    assert settings.app_env == "production"
    assert settings.session_cookie_secure is True
    assert settings.database_url.startswith("postgresql+psycopg://")
