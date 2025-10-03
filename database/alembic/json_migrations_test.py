from typing import Annotated

from pydantic import Tag
from pydantic import create_model

from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from sculptor.database.alembic.json_migrations import get_json_schemas_of_all_nested_models
from sculptor.database.alembic.json_migrations import get_potentially_breaking_changes
from sculptor.database.automanaged import DatabaseModel
from sculptor.primitives.ids import ObjectID


class NestedModelA(SerializableModel):
    field_a: str


class NestedModelB(SerializableModel):
    field_b: str


class NestedModelC(SerializableModel):
    field_c: str


class DatabaseModelA(DatabaseModel):
    object_id: ObjectID
    nested_a: NestedModelA


NestedUnionBC = Annotated[
    Annotated[NestedModelB, Tag("NestedModelB")] | Annotated[NestedModelC, Tag("NestedModelC")],
    build_discriminator(),
]

NestedUnionAC = Annotated[
    Annotated[NestedModelA, Tag("NestedModelA")] | Annotated[NestedModelB, Tag("NestedModelB")],
    build_discriminator(),
]


class DatabaseModelB(DatabaseModel):
    object_id: ObjectID
    nested_b: NestedUnionBC


class DatabaseModelC(DatabaseModel):
    object_id: ObjectID
    nested_c: NestedModelC


def test_equal_json_schemas() -> None:
    database_models = (DatabaseModelA, DatabaseModelB)
    schemas = get_json_schemas_of_all_nested_models(database_models)
    assert len(get_potentially_breaking_changes(schemas, schemas)) == 0


def test_database_model_added() -> None:
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB, DatabaseModelC))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) == 0


def test_database_model_removed() -> None:
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((DatabaseModelB,))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) == 0


def test_nested_model_added_to_union() -> None:
    UpdatedDatabaseModelB = create_model("DatabaseModelB", nested_b=NestedUnionBC, __base__=DatabaseModelB)
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, UpdatedDatabaseModelB))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) == 0


def test_nested_model_removed_from_union() -> None:
    UpdatedDatabaseModelB = create_model("DatabaseModelB", nested_b=NestedModelB, __base__=DatabaseModelB)
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, UpdatedDatabaseModelB))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) > 0


def test_model_replaced_in_union() -> None:
    UpdatedDatabaseModelB = create_model("DatabaseModelB", nested_b=NestedUnionAC, __base__=DatabaseModelB)
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, UpdatedDatabaseModelB))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) > 0


def test_nested_model_replaced_altogether() -> None:
    UpdatedDatabaseModelA = create_model("DatabaseModelA", nested_a=NestedModelB, __base__=DatabaseModelA)
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((UpdatedDatabaseModelA, DatabaseModelB))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) > 0


def test_nested_model_changed_field() -> None:
    UpdatedNestedModelA = create_model("NestedModelA", field_a=NestedModelB, __base__=NestedModelA)
    UpdatedDatabaseModelA = create_model("DatabaseModelA", nested_a=UpdatedNestedModelA, __base__=DatabaseModelA)
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((UpdatedDatabaseModelA, DatabaseModelB))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) > 0


def test_nested_model_unchanged() -> None:
    UpdatedNestedModelA = create_model("NestedModelA", field_a=str, __base__=NestedModelA)
    UpdatedDatabaseModelA = create_model("DatabaseModelA", nested_a=UpdatedNestedModelA, __base__=DatabaseModelA)
    old_schemas = get_json_schemas_of_all_nested_models((DatabaseModelA, DatabaseModelB))
    new_schemas = get_json_schemas_of_all_nested_models((UpdatedDatabaseModelA, DatabaseModelB))
    assert len(get_potentially_breaking_changes(old_schemas, new_schemas)) == 0
