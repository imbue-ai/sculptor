from typing import Annotated

from pydantic import Tag

from sculptor.utils.type_utils import extract_leaf_types


def test_extract_leaf_types_from_simple_type_annotation() -> None:
    assert extract_leaf_types(int) == (int,)


def test_extract_leaf_types_from_complicated_nested_annotation() -> None:
    type_annotation = Annotated[Annotated[int | None, Tag("foo")], Tag("bar")] | str
    assert extract_leaf_types(type_annotation) == (int, type(None), str)


def test_extract_leaf_types_reacts_to_is_everything_expanded() -> None:
    type_annotation = Annotated[Annotated[int | tuple[str, None], Tag("foo")], Tag("bar")]
    assert extract_leaf_types(type_annotation, is_everything_expanded=False) == (int, tuple[str, None])
    assert extract_leaf_types(type_annotation, is_everything_expanded=True) == (int, str, None)
