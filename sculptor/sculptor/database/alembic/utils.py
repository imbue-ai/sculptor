import json
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator

import alembic.script
from alembic import context
from alembic.config import Config

from sculptor.database.alembic.json_migrations import Schemas

FROZEN_SCHEMAS_PATH = Path(__file__).parent / "frozen_pydantic_schemas.json"


@contextmanager
def override_run_env(context_kwargs: dict[str, Any]) -> Generator[Config, None, None]:
    """
    Create an Alembic Config with a given script location and run the specified run_env function instead of the env.py script.

    This is a hack that allows us to run Alembic migrations on existing in-memory SQLite databases.
    The primary use case is tests.

    """

    def run_env(self) -> None:
        context.configure(**context_kwargs)
        with context.begin_transaction():
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


def update_frozen_database_model_nested_json_schemas(schemas: Schemas) -> None:
    content = json.dumps(schemas, sort_keys=True, indent=2) + "\n"
    FROZEN_SCHEMAS_PATH.write_text(content, encoding="utf-8")
