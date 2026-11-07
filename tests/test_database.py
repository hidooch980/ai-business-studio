from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.session import build_engine


def test_sqlite_engine_can_execute_and_create_sessions(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = build_engine(database_url)
    try:
        with Session(engine) as session:
            assert session.execute(text("select 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_engine_creation_does_not_require_database_connectivity() -> None:
    engine = build_engine("postgresql+psycopg://user:pass@127.0.0.1:1/app")
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        engine.dispose()



def test_sqlite_engine_enforces_foreign_keys(tmp_path) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    database_url = f"sqlite:///{tmp_path / 'foreign-keys.db'}"
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
            )
        with engine.begin() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        try:
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO child (parent_id) VALUES (999)"))
        except IntegrityError:
            pass
        else:
            raise AssertionError("SQLite accepted a row with a missing foreign-key parent")
    finally:
        engine.dispose()
