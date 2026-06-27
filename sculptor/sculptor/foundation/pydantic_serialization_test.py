import functools
from threading import Lock
from typing import Collection

import pydantic._internal._fields as pydantic_internal_fields
from inline_snapshot import snapshot
from pydantic import BaseModel
from pydantic import PrivateAttr

import sculptor.foundation.pydantic_serialization  # noqa: F401 -- importing installs the cache
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import model_dump


def test_default_factory_signature_check_is_memoized() -> None:
    # Guards the workaround for the Python-3.14 / pydantic default-factory leak: pydantic calls
    # inspect.signature(default_factory) on EVERY instantiation, and on a C/builtin factory that
    # copies and retains sys.modules -> gigabytes of RSS. pydantic_serialization installs a cache.
    # If pydantic renames the helper (so the cache silently isn't installed), this fails loudly.
    check = pydantic_internal_fields.takes_validated_data_argument
    assert getattr(check, "__sculptor_memoized__", False), (
        "pydantic's takes_validated_data_argument is not memoized -- the Python 3.14 default-factory"
        + " leak workaround in pydantic_serialization is missing or no longer applies to this pydantic version"
    )

    # ...and the cache is effective: the expensive signature check runs once per factory, not per call.
    # (cache_info/cache_clear are added by functools.cache at runtime, so reach them via getattr.)
    getattr(check, "cache_clear")()

    class _Model(BaseModel):
        _lock: Lock = PrivateAttr(default_factory=Lock)

    _Model()
    _Model()
    _Model()
    info = getattr(check, "cache_info")()
    assert info.misses <= 2 and info.hits >= 1, f"default-factory signature check is not being cached: {info}"


def test_unhashable_default_factory_does_not_crash() -> None:
    # The memoization cache keys on the factory object, so an unhashable factory (e.g. a
    # functools.partial) must fall back to the uncached check rather than raising TypeError on
    # instantiation -- which stock pydantic (calling inspect.signature directly) does not do.
    class _Model(BaseModel):
        _data: dict = PrivateAttr(default_factory=functools.partial(dict))

    _Model()
    _Model()  # must not raise


class TestObject(SerializableModel):
    __test__ = False

    name: str
    language_code: str
    inner_data: dict[str, Collection[str]]


def test_simple() -> None:
    obj = TestObject.model_validate(
        dict(name="Filiz", languageCode="tr-TR", innerData={"snake_key": "value", "camelKey": "value"})
    )
    assert model_dump(obj) == snapshot(
        {
            "name": "Filiz",
            "language_code": "tr-TR",
            "inner_data": {"snake_key": "value", "camelKey": "value"},
        }
    )


def test_to_camel() -> None:
    obj = TestObject.model_validate(
        dict(name="Filiz", languageCode="tr-TR", innerData={"snake_key": "value", "camelKey": "value"})
    )
    assert model_dump(obj, is_camel_case=True) == snapshot(
        {
            "name": "Filiz",
            "languageCode": "tr-TR",
            "innerData": {"snake_key": "value", "camelKey": "value"},
        }
    )


def test_reversible() -> None:
    obj = TestObject.model_validate(
        dict(name="Filiz", languageCode="tr-TR", innerData={"snake_key": "value", "camelKey": "value"})
    )
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
