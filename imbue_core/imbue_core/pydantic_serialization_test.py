from typing import Collection

from inline_snapshot import snapshot

from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import model_dump


class TestObject(SerializableModel):
    __test__ = False

    name: str
    language_code: str
    inner_data: dict[str, Collection[str]]


def test_simple() -> None:
    # pyre-ignore[6]: pyre is confused by the snake --> camel case conversion, so using a TypedDict doesn't work, so just ignore
    obj = TestObject(**dict(name="Filiz", languageCode="tr-TR", innerData={"snake_key": "value", "camelKey": "value"}))
    assert model_dump(obj) == snapshot(
        {
            "name": "Filiz",
            "language_code": "tr-TR",
            "inner_data": {"snake_key": "value", "camelKey": "value"},
        }
    )


def test_to_camel() -> None:
    # pyre-ignore[6]: pyre is confused by the snake --> camel case conversion, so using a TypedDict doesn't work, so just ignore
    obj = TestObject(**dict(name="Filiz", languageCode="tr-TR", innerData={"snake_key": "value", "camelKey": "value"}))
    assert model_dump(obj, is_camel_case=True) == snapshot(
        {
            "name": "Filiz",
            "languageCode": "tr-TR",
            "innerData": {"snake_key": "value", "camelKey": "value"},
        }
    )


def test_reversible() -> None:
    # pyre-ignore[6]: pyre is confused by the snake --> camel case conversion, so using a TypedDict doesn't work, so just ignore
    obj = TestObject(**dict(name="Filiz", languageCode="tr-TR", innerData={"snake_key": "value", "camelKey": "value"}))
    assert TestObject.model_validate(model_dump(obj)) == obj


def test_evolve() -> None:
    obj = TestObject(
        name="Filiz",
        language_code="tr-TR",
        inner_data={"snake_key": "value", "camelKey": "value"},
    )
    new_obj = obj.evolve(obj.ref().name, "thing")
    assert new_obj.name == "thing"
    assert obj.name == "Filiz"
