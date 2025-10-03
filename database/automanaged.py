"""
Functionality enabling the two-table pattern for our database models.
(Refer to the docstring in core.py for more details.)

To use this:
    - Create a pydantic model that inherits from DatabaseModel.
    - Call create_tables() with the model class.

Under the hood, the `create_tables()` call will:
    - infer a set of column definitions from the pydantic model.
    - register the two tables (one for the snapshots and one for the latest versions) with SQLAlchemy.
    - register a database trigger to automatically update the latest table on insert into the snapshots table.

The actual _creation_ of the tables and the triggers happens later on when the database is initialized. (Via `initialize_db()` in core.py.)

In case the type of a field in your pydantic model is not supported out of the box, add a new entry in _PYDANTIC_TO_SQLALCHEMY_TYPES.

NOTE: Never update records in the snapshots table. (Only insert.)

"""

import inspect
from abc import ABC
from datetime import datetime
from typing import TypeVar
from typing import get_type_hints

from pydantic import AnyUrl
from pydantic import ConfigDict
from pydantic import EmailStr
from pydantic import Field
from pydantic import HttpUrl
from sqlalchemy import Column
from sqlalchemy import Constraint
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.schema import DDL

from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.time_utils import get_current_time
from sculptor.database.core import METADATA
from sculptor.primitives.ids import ObjectID
from sculptor.primitives.ids import ObjectSnapshotID
from sculptor.utils.type_utils import extract_leaf_types

OBJECT_ID = "object_id"
SNAPSHOT_ID = "snapshot_id"
CREATED_AT = "created_at"

# List of model classes that are automatically managed by the two-table pattern.
# (Gets populated by the create_tables() function, alongside METADATA.)
AUTOMANAGED_MODEL_CLASSES: set[type["DatabaseModel"]] = set()


T = TypeVar("T", bound=SerializableModel)

_PYDANTIC_TO_SQLALCHEMY_TYPES = {
    ObjectID: String,
    SerializableModel: JSON,
    HttpUrl: String,
    EmailStr: String,
    AnyUrl: String,
    int: Integer,
    float: Float,
    datetime: DateTime(timezone=True),
    str: String,
    # Add more type mappings as needed.
}


class DatabaseModel(SerializableModel, ABC):
    """Base class for database models."""

    model_config = ConfigDict(
        frozen=True,
        # We allow "arbitrary" types in order to support ObjectID.
        # In practice, the types are checked by the SQLAlchemy type mapping, anyway.
        arbitrary_types_allowed=True,
    )

    created_at: datetime = Field(default_factory=get_current_time)

    def __init_subclass__(cls) -> None:
        """
        Ensure that the subclass defines an 'object_id' attribute of type ObjectID.

        """
        super().__init_subclass__()
        hints = get_type_hints(cls)
        obj_id_type = hints.get("object_id")
        if obj_id_type is None:
            raise InvalidDatabaseModelDefinitionError(f"{cls.__name__} must define the 'object_id' attribute.")
        if not inspect.isclass(obj_id_type) or not issubclass(obj_id_type, ObjectID):
            raise InvalidDatabaseModelDefinitionError(f"'object_id' in {cls.__name__} must be a subclass of ObjectID.")

    def is_content_equal(self, other: "DatabaseModel") -> bool:
        all_fields = vars(self)
        # this is a list of fields in case you want to exclude some other fields in the future.
        excluded_fields = ("created_at",)
        return all(
            getattr(self, field) == getattr(other, field) for field in all_fields if field not in excluded_fields
        )


class UnsupportedAutomanagedTypeError(Exception):
    pass


class InvalidDatabaseModelDefinitionError(Exception):
    pass


def _get_sqlalchemy_type(pydantic_type: type) -> tuple[type, bool]:
    if pydantic_type in _PYDANTIC_TO_SQLALCHEMY_TYPES:
        return _PYDANTIC_TO_SQLALCHEMY_TYPES[pydantic_type], False
    leaf_types = extract_leaf_types(pydantic_type)
    is_nullable = type(None) in leaf_types
    args = tuple(arg for arg in leaf_types if arg is not type(None))
    for base_type, sqlalchemy_type in _PYDANTIC_TO_SQLALCHEMY_TYPES.items():
        if all(issubclass(arg, base_type) for arg in args):
            return sqlalchemy_type, is_nullable

    raise UnsupportedAutomanagedTypeError(f"Unsupported Pydantic type: {pydantic_type}")


class InvalidFieldsError(Exception):
    pass


def create_tables(
    table_name: str,
    model_cls: type[DatabaseModel],
    constraints: tuple[Constraint, ...] = (),
    is_dual_table: bool = True,
) -> tuple[Table, Table]:
    """
    Create the main table with snapshots,
    as well as the _latest table with the most recent object versions (if is_dual_table is True).

    When is_dual_table is False, only the main table is created.
    """
    # Iterate over the fields of the Pydantic model and create SQLAlchemy columns.
    base_columns: list[Column] = []
    for field_name, field in model_cls.model_fields.items():
        pydantic_type = field.annotation
        assert pydantic_type is not None, f"Field {field_name} has no type annotation"
        column_type, is_nullable = _get_sqlalchemy_type(pydantic_type)
        if field_name == CREATED_AT:
            # We only need the default factory for CREATED_AT because sqlite cannot set fields in the BEFORE trigger.
            assert is_nullable == False
            base_columns.append(Column(field_name, column_type, nullable=False, default=field.default_factory))
        else:
            # If we ever need nulls, we'll need to add support for them.
            base_columns.append(Column(field_name, column_type, nullable=is_nullable))

    # when this is a dual table, the constraints are applied to the latest table.
    if is_dual_table:
        full_table_constraints = []
        latest_table_constraints = constraints
    # If this is not a dual table, the constraints are applied to the main table.
    else:
        full_table_constraints = constraints
        latest_table_constraints = []

    snapshots_table = Table(
        table_name,
        METADATA,
        Column(SNAPSHOT_ID, String, primary_key=True, default=lambda: str(ObjectSnapshotID())),
        *base_columns,
        *full_table_constraints,
    )
    base_columns_copy = [
        Column(
            column.name,
            column.type,
            primary_key=column.primary_key,
            nullable=column.nullable,
            default=column.default if column.default is not None else None,
        )
        for column in base_columns
    ]
    for column in base_columns_copy:
        if column.name == OBJECT_ID:
            column.primary_key = True
            break
    else:
        raise InvalidFieldsError(f"Field {OBJECT_ID} not found.")
    if is_dual_table:
        psql_trigger = _get_psql_trigger(table_name, tuple(base_columns))
        sqlite_triggers = _get_sqlite_triggers(table_name, tuple(base_columns))
        latest_table = Table(
            _get_latest_table_name(table_name),
            METADATA,
            *base_columns_copy,
            *latest_table_constraints,
        )
        # We used to store this directly in Table.info but that resulted in Alembic dumping the triggers in the migration files.
        METADATA.info.setdefault("triggers", {})[table_name] = {
            "sqlite": sqlite_triggers,
            "postgresql": (psql_trigger,),
        }
    else:
        latest_table = snapshots_table
    AUTOMANAGED_MODEL_CLASSES.add(model_cls)
    return snapshots_table, latest_table


def _get_latest_table_name(base_table_name: str) -> str:
    return f"{base_table_name}_latest"


def _get_psql_trigger(table_name: str, base_columns: tuple[Column, ...]) -> DDL:
    function_name = f"refresh_{_get_latest_table_name(table_name)}"
    base_column_names = ", ".join([col.name for col in base_columns])
    base_column_values = ", ".join([f"NEW.{col.name}" for col in base_columns])
    update_statements = ", ".join(
        [f"{col.name} = EXCLUDED.{col.name}" for col in base_columns if col.name not in (OBJECT_ID, CREATED_AT)]
    )
    return DDL(
        f"""
        CREATE OR REPLACE FUNCTION {function_name}()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO {_get_latest_table_name(table_name)} (
                {base_column_names}
            ) VALUES (
                {base_column_values}
            )
            ON CONFLICT ({OBJECT_ID}) DO UPDATE SET
                {update_statements};
            NEW.{CREATED_AT} = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DO $$
        BEGIN
            CREATE TRIGGER {table_name}_before_insert
            BEFORE INSERT ON "{table_name}"
            FOR EACH ROW
            EXECUTE FUNCTION {function_name}();
        EXCEPTION
            WHEN duplicate_object THEN
            RAISE NOTICE 'Trigger already exists, skipping creation.';
        END $$;
        """
    )


def _get_sqlite_triggers(table_name: str, base_columns: tuple[Column, ...]) -> tuple[DDL, ...]:
    base_column_names = ", ".join([col.name for col in base_columns])
    base_column_values = ", ".join([f"NEW.{col.name}" for col in base_columns])
    update_statements = ", ".join(
        [f"{col.name} = excluded.{col.name}" for col in base_columns if col.name not in (OBJECT_ID, CREATED_AT)]
    )
    # TODO: we need to come back to this when we start having multiple processes writing to the same database.
    # The initialization code runs on every server startup.
    # Dropping the triggers is a little dubious but in the case of sqlite, the assumption is that
    # the database is not used by other processes at the same time.
    # Eventually, we should manage DB state differently. (E.g. using alembic?)
    drop_existing_before_insert_trigger = DDL(f"DROP TRIGGER IF EXISTS {table_name}_before_insert;")
    before_insert_trigger = DDL(
        f"""
        CREATE TRIGGER {table_name}_before_insert
        BEFORE INSERT ON {table_name}
        BEGIN
            INSERT INTO {_get_latest_table_name(table_name)} (
                {base_column_names}
            ) VALUES (
                {base_column_values}
            )
            ON CONFLICT ({OBJECT_ID}) DO UPDATE SET
                {update_statements};
        END;
        """
    )

    # Do this to respect the semantics of created_at in the latest table.
    # (Unlike Postgres, SQLite does not support setting fields in the BEFORE trigger.)
    drop_existing_after_insert_trigger = DDL(f"DROP TRIGGER IF EXISTS set_{table_name}_created_at;")
    after_insert_trigger = DDL(
        f"""
        CREATE TRIGGER set_{table_name}_created_at
        AFTER INSERT ON {table_name}
        FOR EACH ROW
        BEGIN
            UPDATE {table_name}
            SET created_at = datetime('now')
            WHERE {SNAPSHOT_ID} = NEW.{SNAPSHOT_ID};
        END;
        """
    )
    return (
        drop_existing_before_insert_trigger,
        before_insert_trigger,
        drop_existing_after_insert_trigger,
        after_insert_trigger,
    )
