"""
This module contains functions for tracking and managing the evolution of JSON schemas of the nested pydantic models.

"""

import json
from typing import Any

from imbue_core.pydantic_serialization import SerializableModel
from sculptor.utils.type_utils import extract_leaf_types

Schema = dict[str, dict[str, dict[str, Any]]]

Schemas = dict[str, Schema]


def get_json_schemas_of_all_nested_models(database_model_classes: tuple[type[SerializableModel], ...]) -> Schemas:
    """
    Dumps JSON schemas of all nested models in the database. Sorted by model name + field name.

    Returns a nested dictionary with the structure:
    {
        "<database_model_name>": {
            "<field_name>": {
                "<nested_model_name>": <json_schema_object>
            }
        }
    }

    """
    schemas: Schemas = {}
    for database_model in database_model_classes:
        for field_name, field in database_model.model_fields.items():
            leaf_types = extract_leaf_types(field.annotation)
            for leaf_type in leaf_types:
                # If it's a SerializableModel, we can dump its schema.
                if issubclass(leaf_type, SerializableModel):
                    schema = leaf_type.model_json_schema()
                    if database_model.__name__ not in schemas:
                        schemas[database_model.__name__] = {}
                    if field_name not in schemas[database_model.__name__]:
                        schemas[database_model.__name__][field_name] = {}
                    schemas[database_model.__name__][field_name][leaf_type.__name__] = schema
    return schemas


def get_potentially_breaking_changes(old_schemas: Schemas, new_schemas: Schemas) -> tuple[str, ...]:
    """
    Checks if the new schemas are potentially breaking compatibility with the old schemas.

    Args:
        old_schemas (Schemas): The old schemas.
        new_schemas (Schemas): The new schemas.

    Returns: A tuple of string messages describing the potentially breaking changes.

    Specifically:
        - If a database model has been entirely removed or added, it's considered compatible (since it would be caught by SQL schema migration).
        - If a field in a database model has been entirely removed or added, it's considered compatible for the same reason.
        - If the structure of a field's has changed, it is considered potentially breaking.
        - ...unless the change is just adding a new SerializableModel to a union of types, which is considered compatible.
        (In practice, other changes can also be compatible, but we can't guarantee that easily so we prefer reporting that to the developer.)
    """

    SKIPPED_CHECKS = {("CommandInputUserMessage", "message", "SavedAgentMessage")}

    messages: list[str] = []
    for model_name, old_model_schema in old_schemas.items():
        if model_name not in new_schemas:
            continue  # Model has been removed, considered compatible.

        new_model_schema = new_schemas[model_name]

        for field_name, old_field_schema in old_model_schema.items():
            if field_name not in new_model_schema:
                continue  # Field has been removed, considered compatible.

            new_field_schema = new_model_schema[field_name]

            for old_type_name, old_type_schema in old_field_schema.items():
                if (old_type_name, field_name, model_name) in SKIPPED_CHECKS:
                    # Potentially breaking, but has been hardcoded and we know it's fine.
                    continue
                if old_type_name not in new_field_schema:
                    messages.append(
                        f"Type '{old_type_name}' has been removed from field '{field_name}' of model '{model_name}'."
                    )
                    continue

                new_type_schema = new_field_schema[old_type_name]

                # drop the description fields because they can change without breaking anything
                if "description" in old_type_schema:
                    del old_type_schema["description"]
                if "description" in new_type_schema:
                    del new_type_schema["description"]

                if json.dumps(old_type_schema, sort_keys=True) != json.dumps(new_type_schema, sort_keys=True):
                    messages.append(
                        f"Schema of type '{old_type_name}' has changed for field '{field_name}' of model '{model_name}'."
                    )

    return tuple(messages)
