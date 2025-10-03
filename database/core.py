"""
Define core database functionality for the application.

Initial design decisions (ask Josh in case of questions):
    - We are going to use a subset of SQLAlchemy.
        - Mostly just for table definitions, DB management and query building.
        - Specifically, we're not going to use the ORM features of SQLAlchemy.
        - Reason: we think that ORMs are too heavy-handed and opaque.
        - Also, with an ORM, we lose control over the exposed DB operations.
            - (Having a limited set of specialized functions makes the intended use of the DB clearer.)
    - Each object type is stored in a pair of tables:
        - The main table holds immutable "snapshots" of the objects.
        - The second table stores the most recent version of each object.
        - The immutable table is the "source of truth". The mutable table exists for convenience to offer a view at the "current" state.
            - Also, we use the mutable table to define unique constraints, foreign keys, etc.
        - The mutable table is named <table_name>_latest and is populated automatically using database triggers.
        - This setup is achieved through the `database/automanaged.py` module.

"""

import sqlite3

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import Engine
from sqlalchemy import MetaData
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from sculptor.database.alembic.utils import get_alembic_script_location
from sculptor.database.alembic.utils import override_run_env

METADATA = MetaData()


IN_MEMORY_SQLITE = "sqlite:///:memory:"


def create_new_engine(database_url: str) -> Engine:
    """
    Create the SQLAlchemy engine.

    Be careful not to needlessly create new engines.

    """
    if database_url == IN_MEMORY_SQLITE:
        engine = create_engine(
            database_url,
            poolclass=NullPool,
            connect_args={
                "check_same_thread": False,
                # the default is 5.0 seconds.
                # I'm bumping it a little bit here so that we can avoid dealing with contention if very busy
                # we WILL need to come back to this...
                "timeout": 10.0,
            },
        )
    else:
        engine = create_engine(
            database_url,
            poolclass=NullPool,
            echo=False,
            # We add pool_recycle to dispose of stale neon.tech connections.
            # (In neon.tech, when "Scale to zero" is enabled, the DB is stopped after 5 minutes of inactivity.)
            # This is more efficient than using pool_pre_ping.
            pool_recycle=60 * 5 - 10,
        )
    # In case it's sqlite, we need to enable foreign key constraints.
    if engine.name == "sqlite":
        event.listens_for(engine, "connect")(_enable_foreign_keys_in_sqlite)
    return engine


def _enable_foreign_keys_in_sqlite(dbapi_connection: sqlite3.Connection, connection_record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def initialize_db_from_connection(connection: Connection, dialect: str, database_url: str) -> None:
    if database_url != IN_MEMORY_SQLITE:
        # For non-in-memory databases, we run migrations in the standard Alembic way.
        _run_migrations_on_database_url(database_url, script_location=get_alembic_script_location())
    else:
        # For in-memory SQLite, we have to run migrations directly on the connection.
        # (Otherwise, Alembic would try to create a new in-memory database, which would not have the tables we need.)
        _run_migrations_on_connection(connection)
    triggers_info = METADATA.info.get("triggers", {})
    for table in METADATA.tables.values():
        triggers = triggers_info.get(table.name, {}).get(dialect)
        if triggers is not None:
            for trigger in triggers:
                connection.execute(trigger)


def initialize_db(engine: Engine) -> None:
    """
    Initialize the database, creating tables, functions and triggers if needed.

    We do this at server startup (including running the migrations).
    Eventually, when we support remote servers (and not just locally running sculptor instances), we should re-evaluate this.

    For more details about migrations, refer to `sculptor/database/README.md`.

    """
    dialect = engine.dialect.name
    if dialect == "sqlite" and engine.url != IN_MEMORY_SQLITE:
        with engine.connect() as connection:
            # The WAL journal mode is persistent so it's enough to set this pragma just once.
            # https://linear.app/imbue/issue/PROD-540/attempt-to-fix-db-locking-using-wal
            connection.execute(text("PRAGMA journal_mode = WAL"))
    with engine.begin() as connection:
        initialize_db_from_connection(connection, dialect, str(engine.url))


def _run_migrations_on_database_url(database_url: str, script_location: str) -> None:
    config = Config()
    config.set_main_option("script_location", script_location)
    config.set_main_option("sqlalchemy.url", database_url)
    try:
        command.upgrade(config, "head")
    except Exception as e:
        raise MigrationsFailedError(f"Failed to run migrations on {database_url}: {e}") from e


def _run_migrations_on_connection(connection: Connection) -> None:
    with override_run_env({"connection": connection, "target_metadata": None}) as config:
        try:
            command.upgrade(config, "head")
        except Exception as e:
            raise MigrationsFailedError(f"Failed to run migrations: {e}") from e


class MigrationsFailedError(Exception):
    @property
    def is_likely_a_result_of_sculptor_downgrade(self):
        cause = self.__cause__
        return isinstance(cause, CommandError) and "Can't locate revision identified by" in str(cause)
