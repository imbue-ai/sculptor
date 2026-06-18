from collections.abc import Mapping
from typing import Any
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def model_update(model: T, update: Mapping[str, Any]) -> T:
    """Return a copy of the model with the given field updates applied.

    Validation ensures every key in the update is a real field of the model.
    For nested, type-checked updates, use the Evolver class in
    sculptor.foundation.nested_evolver.
    """
    extra_fields = update.keys() - set(model.__class__.model_fields)
    if extra_fields:
        raise ValueError(f"Invalid fields: {extra_fields}")
    return fields_only_model_copy(model, update=update)


def fields_only_model_copy(model: T, update: Mapping[str, Any] | None = None) -> T:
    """Create a copy of a Pydantic model with only its declared fields (not cached properties)."""
    field_updates = update if update is not None else {}
    fields = {name: field_updates.get(name, getattr(model, name)) for name in model.__class__.model_fields}
    return model.__class__(**fields)
