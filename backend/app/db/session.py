from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


def build_engine(database_url: str) -> Engine:
    """Build an engine without opening a connection.

    SQLite is intended for a single local application node only. PostgreSQL is
    the supported shared database for multi-user and multi-branch deployments.
    """
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL must be configured before database access")
    return build_engine(url)


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
