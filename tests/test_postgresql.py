import os

import pytest
from sqlalchemy import text

from backend.app.db.session import build_engine


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL CI service is not configured")
def test_postgresql_connection_and_transaction() -> None:
    engine = build_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as connection:
            assert connection.execute(text("select 1")).scalar_one() == 1
    finally:
        engine.dispose()
