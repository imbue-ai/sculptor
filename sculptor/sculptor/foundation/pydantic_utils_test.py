import pytest
from pydantic import BaseModel

from sculptor.foundation.pydantic_utils import model_update


def test_model_update_succeeds() -> None:
    class MyModel(BaseModel):
        field1: int
        field2: str

    original_model = MyModel(field1=1, field2="test")
    update = {"field1": 2}

    updated_model = model_update(original_model, update)

    assert updated_model.field1 == 2
    assert updated_model.field2 == "test"


def test_model_update_unknown_fields() -> None:
    class MyModel(BaseModel):
        field1: int
        field2: str

    original_model = MyModel(field1=1, field2="test")
    update = {"field4": 2}

    with pytest.raises(ValueError):
        model_update(original_model, update)
