import json
import types
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator

import alembic.script
from alembic import context
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection

from sculptor.database.alembic.json_migrations import Schemas

FROZEN_SCHEMAS_PATH = Path(__file__).parent / "frozen_pydantic_schemas.json"


class EmptyFrozenSchemasError(ValueError):
    """Raised when attempting to persist an empty frozen JSON-schema baseline.

    An empty baseline silently disables the JSON-column durability guard
    (``get_potentially_breaking_changes`` only inspects keys present in the
    baseline), which is how the guard was disarmed in SCU-1523. An empty result
    almost always means the automanaged-model registry was not populated (import
    ``sculptor.services.data_model_service.sql_implementation`` before regenerating).
    """


def drop_all_automanaged_triggers(connection: Connection) -> None:
    """Drop every database trigger before migrations run.

    Auto-managed tables (see ``database/automanaged.py``) carry triggers whose bodies
    reference *every* column of the table — e.g. ``<table>_before_insert`` references
    ``NEW.<col>`` for each column. SQLite validates trigger bodies during ``ALTER TABLE``,
    so dropping or renaming any referenced column fails while such a trigger exists. That
    made every column-dropping migration responsible for manually dropping its triggers
    first — a forgettable step that broke startup more than once.

    We make that class of failure impossible by guaranteeing the invariant that no trigger
    exists while migrations run. The triggers are recreated from the current model right
    after migrations by ``initialize_db_from_connection()``. This also matches what
    migrations already assume — e.g. one migration populates ``<table>_latest`` by hand
    with the comment "triggers don't exist during migration", which is only true on a fresh
    install; this makes it true on upgrades too.

    Every trigger in this database is part of the auto-managed dual-table pattern, so it is
    safe to drop them all here.
    """
    if connection.dialect.name != "sqlite":
        return
    trigger_names = [
        row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))
    ]
    for name in trigger_names:
        connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}"'))


@contextmanager
def override_run_env(context_kwargs: Mapping[str, Any]) -> Generator[Config, None, None]:
    """
    Create an Alembic Config with a given script location and run the specified run_env function instead of the env.py script.

    This is a hack that allows us to run Alembic migrations on existing in-memory SQLite databases.
    The primary use case is tests.

    """

    def run_env(self) -> None:
        context.configure(**context_kwargs)
        with context.begin_transaction():
            connection = context_kwargs.get("connection")
            if connection is not None:
                drop_all_automanaged_triggers(connection)
            context.run_migrations()

    config = Config()
    script_location = get_alembic_script_location()
    config.set_main_option("script_location", script_location)
    original_run_env = alembic.script.ScriptDirectory.run_env
    alembic.script.ScriptDirectory.run_env = types.MethodType(
        run_env, alembic.script.ScriptDirectory(Path(script_location))
    )
    try:
        yield config
    finally:
        alembic.script.ScriptDirectory.run_env = original_run_env


def get_alembic_script_location() -> str:
    return str(Path(__file__).parent)


def get_frozen_database_model_nested_json_schemas() -> Schemas:
    return json.loads(FROZEN_SCHEMAS_PATH.read_text(encoding="utf-8"))


_EMPTY_SCHEMAS_MESSAGE = "Refusing to overwrite the frozen JSON-schema baseline with an empty schema set: this would silently disable the JSON-column durability guard. The automanaged-model registry was likely not populated (import sculptor.services.data_model_service.sql_implementation before regenerating)."


def update_frozen_database_model_nested_json_schemas(schemas: Schemas) -> None:
    if not schemas:
        raise EmptyFrozenSchemasError(_EMPTY_SCHEMAS_MESSAGE)
    content = json.dumps(schemas, sort_keys=True, indent=2) + "\n"
    FROZEN_SCHEMAS_PATH.write_text(content, encoding="utf-8")
