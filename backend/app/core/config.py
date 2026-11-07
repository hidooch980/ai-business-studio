import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    log_level: str
    database_url: str | None


@lru_cache
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    return Settings(
        app_name=os.getenv("APP_NAME", "AI Business Studio"),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database_url=database_url.strip() if database_url and database_url.strip() else None,
    )
