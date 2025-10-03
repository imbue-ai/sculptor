from pydantic import BaseModel

from sculptor.utils.type_utils import extract_leaf_types


class OptionalModel(BaseModel):
    field_via_optional: str | None = None
    field_via_union: str | None = None


def test_extract_leaf_types_with_optional() -> None:
    for field_name, field in OptionalModel.model_fields.items():
        pydantic_type = field.annotation
        leaf_types = extract_leaf_types(pydantic_type)
        is_nullable = type(None) in leaf_types
        assert is_nullable
