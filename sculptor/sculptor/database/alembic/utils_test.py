import pytest

from sculptor.database.alembic.utils import update_frozen_database_model_nested_json_schemas


def test_update_frozen_schemas_refuses_to_write_empty_baseline() -> None:
    """Persisting an empty baseline silently disables the JSON-column durability guard.

    An empty ``frozen_pydantic_schemas.json`` makes ``get_potentially_breaking_changes``
    inert (it only inspects keys present in the baseline), which is exactly how the guard
    was disarmed in SCU-1523. The write helper must refuse to overwrite the committed
    baseline with ``{}`` rather than silently disabling the guard.
    """
    with pytest.raises(ValueError):
        update_frozen_database_model_nested_json_schemas({})
