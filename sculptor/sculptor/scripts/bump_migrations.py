"""
Run this script to generate missing migrations.

Please manually review the generated migration files before committing. Make sure that:
    - The logic seems correct wrt. the changes you made to the models.

Afterwards, you can test the migration by running:

    uv run alembic -x dburl=sqlite:///~/.sculptor/database.db upgrade head

From the `sculptor/database` directory. (It may be better to back up your original DB first.)

"""

import importlib
import re
from pathlib import Path

import typer
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from loguru import logger
from sqlalchemy import Connection

from sculptor.database.alembic.json_migrations import get_json_schemas_of_all_nested_models
from sculptor.database.alembic.json_migrations import get_potentially_breaking_changes
from sculptor.database.alembic.migration_test_utils import VERSIONS_DIR
from sculptor.database.alembic.migration_test_utils import VERSION_TESTS_DIR
from sculptor.database.alembic.utils import FROZEN_SCHEMAS_PATH
from sculptor.database.alembic.utils import get_frozen_database_model_nested_json_schemas
from sculptor.database.alembic.utils import override_run_env
from sculptor.database.alembic.utils import update_frozen_database_model_nested_json_schemas
from sculptor.database.automanaged import AUTOMANAGED_MODEL_CLASSES
from sculptor.database.core import IN_MEMORY_SQLITE
from sculptor.database.core import METADATA
from sculptor.database.core import create_new_engine
from sculptor.database.core import initialize_db_from_connection
from sculptor.services.data_model_service.sql_implementation import register_all_tables


def main(migration_message: str) -> None:
    is_sql_schema_migration_needed, connection = _is_sql_schema_migration_needed()
    potentially_breaking_json_schema_changes = _get_potentially_breaking_json_schema_changes()
    is_json_schema_migration_needed = len(potentially_breaking_json_schema_changes) > 0
    if not is_sql_schema_migration_needed and not is_json_schema_migration_needed:
        connection.close()
        logger.info("No migrations needed. All schemas are compatible.")
        return
    logger.info("Autogenerating migrations...")
    try:
        _autogenerate_migrations(connection, migration_message)
    finally:
        connection.close()
    _generate_test_stub()
    if is_sql_schema_migration_needed:
        logger.info("Generated SQL schema migration. Please review before committing.")
    if is_json_schema_migration_needed:
        _update_frozen_schemas()
        logger.info(
            "\n".join(
                [
                    "Following potentially breaking changes were detected in JSON schemas:",
                    "- " + "\n - ".join(potentially_breaking_json_schema_changes),
                    "Please supply the actual migration logic for the JSON schema migration.",
                    "For an example json schema migration, see `sculptor/database/alembic/examples/json_schema_migration.py`.",
                    "It is also possible that the json schema migration is not needed at all.",
                    "In that case, you can just remove the migration file."
                    if not is_sql_schema_migration_needed
                    else "",
                    "Please review the changes in the frozen_json_schemas.json file to determine if the migration is needed and what exactly needs to be done.",
                ]
            )
        )


def _is_sql_schema_migration_needed() -> tuple[bool, Connection]:
    logger.info("Initialize a fresh in-memory DB by running all the existing migrations from scratch...")
    engine = create_new_engine(IN_MEMORY_SQLITE)
    connection = engine.connect()
    register_all_tables()
    initialize_db_from_connection(connection, str(engine.url))
    migration_context = MigrationContext.configure(connection=connection)
    schema_differences = compare_metadata(migration_context, METADATA)
    return bool(schema_differences), connection


def _get_potentially_breaking_json_schema_changes() -> tuple[str, ...]:
    frozen_schemas = get_frozen_database_model_nested_json_schemas()
    latest_schemas = get_json_schemas_of_all_nested_models(tuple(AUTOMANAGED_MODEL_CLASSES))
    return get_potentially_breaking_changes(frozen_schemas, latest_schemas)


def _autogenerate_migrations(connection: Connection, migration_message: str) -> None:
    with override_run_env({"connection": connection, "target_metadata": METADATA}) as config:
        logger.info("Running the alembic revision command to generate a new migration...")
        command.revision(config, message=migration_message, autogenerate=True)


def _generate_test_stub() -> None:
    """Find the most recently generated migration and create a companion test fixture stub."""
    migration_pattern = re.compile(r"^([a-f0-9]+)_.+\.py$")

    # Find the newest migration file by modification time.
    newest_path: Path | None = None
    newest_mtime = 0.0
    for path in VERSIONS_DIR.iterdir():
        if path.is_file() and migration_pattern.match(path.name):
            mtime = path.stat().st_mtime
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest_path = path

    if newest_path is None:
        logger.warning("Could not find any migration files to generate a test stub for.")
        return

    # Import the migration module to read revision and down_revision.
    module_name = f"sculptor.database.alembic.versions.{newest_path.stem}"
    module = importlib.import_module(module_name)
    revision_id: str = module.revision
    down_revision: str | tuple[str, ...] | None = module.down_revision

    # Format the down_revision for the test stub.
    if down_revision is None:
        down_rev_type = "None"
        down_rev_value = "None"
    elif isinstance(down_revision, tuple):
        types = ", ".join(["str"] * len(down_revision))
        down_rev_type = f"tuple[{types}]"
        values = ", ".join(f'"{r}"' for r in down_revision)
        down_rev_value = f"({values})"
    else:
        down_rev_type = "str"
        down_rev_value = f'"{down_revision}"'

    test_file = VERSION_TESTS_DIR / f"test_{revision_id}.py"
    if test_file.exists():
        logger.info("Test fixture already exists at {}.", test_file)
        return

    test_file.write_text(
        f'''\
import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration{revision_id}(MigrationTestFixture):
    """Test fixture for migration {revision_id}.

    Fill in seed() and verify() to test data preservation.
    See database/README.md for guidance on writing fixtures.
    """

    @property
    def revision(self) -> str:
        return "{revision_id}"

    @property
    def down_revision(self) -> {down_rev_type}:
        return {down_rev_value}

    def seed(self, connection: sa.engine.Connection) -> None:
        raise NotImplementedError("Fill in seed() with test data for migration {revision_id}")

    def verify(self, connection: sa.engine.Connection) -> None:
        raise NotImplementedError("Fill in verify() with assertions for migration {revision_id}")
'''
    )
    logger.info("Generated test fixture stub at {}.", test_file)


def _update_frozen_schemas() -> None:
    latest_schemas = get_json_schemas_of_all_nested_models(tuple(AUTOMANAGED_MODEL_CLASSES))
    update_frozen_database_model_nested_json_schemas(latest_schemas)
    logger.info("Updated frozen JSON schemas at {}.", FROZEN_SCHEMAS_PATH)


if __name__ == "__main__":
    typer.run(main)
