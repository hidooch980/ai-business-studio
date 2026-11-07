import os
from dataclasses import dataclass
from functools import lru_cache


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    log_level: str
    database_url: str | None
    session_cookie_name: str
    csrf_cookie_name: str
    session_cookie_secure: bool
    session_lifetime_seconds: int
    allow_public_registration: bool


@lru_cache
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    lifetime = int(os.getenv("SESSION_LIFETIME_SECONDS", "43200"))
    if not 300 <= lifetime <= 2592000:
        raise ValueError("SESSION_LIFETIME_SECONDS must be between 300 and 2592000")
    return Settings(
        app_name=os.getenv("APP_NAME", "AI Business Studio"),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database_url=database_url.strip() if database_url and database_url.strip() else None,
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "abs_session"),
        csrf_cookie_name=os.getenv("CSRF_COOKIE_NAME", "abs_csrf"),
        session_cookie_secure=_env_bool("SESSION_COOKIE_SECURE", True),
        session_lifetime_seconds=lifetime,
        allow_public_registration=_env_bool("ALLOW_PUBLIC_REGISTRATION", False),
    )
