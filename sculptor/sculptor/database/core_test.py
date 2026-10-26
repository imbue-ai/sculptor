"""Running the migrations against the database a caller names by URL."""

from pathlib import Path

from sqlalchemy import inspect

from sculptor.database.core import IN_MEMORY_SQLITE
from sculptor.database.core import create_new_engine
from sculptor.database.core import initialize_db
from sculptor.database.core import initialize_db_from_connection


def test_an_in_memory_database_named_by_its_rendered_url_is_migrated_on_the_given_connection() -> None:
    """`str(engine.url)` spells `:memory:` percent-encoded. Migrating through a fresh
    connection instead would fill a different, throwaway in-memory database."""
    engine = create_new_engine(IN_MEMORY_SQLITE)
    with engine.begin() as connection:
        initialize_db_from_connection(connection, str(engine.url))
        assert "alembic_version" in inspect(connection).get_table_names()


def test_a_database_whose_rendered_url_is_percent_encoded_is_migrated(tmp_path: Path) -> None:
    """SQLAlchemy percent-encodes characters such as non-ASCII letters when it renders a URL."""
    database_path = tmp_path / "jöe" / "database.db"
    database_path.parent.mkdir()
    engine = create_new_engine(f"sqlite:///{database_path}")
    initialize_db(engine)
    assert "alembic_version" in inspect(engine).get_table_names()
