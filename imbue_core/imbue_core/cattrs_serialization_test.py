import asyncio
import base64
import datetime
from enum import IntEnum
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Generic
from typing import Literal
from typing import Mapping
from typing import Optional
from typing import TypeVar
from uuid import UUID

import anyio
import attr
import pytest
from cachetools import LRUCache
from pydantic import HttpUrl
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from imbue_core.cattrs_serialization import DONT_SERIALIZE
from imbue_core.cattrs_serialization import SERIALIZE_WITH_DEFAULT
from imbue_core.cattrs_serialization import SerializationError
from imbue_core.cattrs_serialization import SerializedException
from imbue_core.cattrs_serialization import cached_serializable_property
from imbue_core.cattrs_serialization import deserialize_from_json
from imbue_core.cattrs_serialization import serializable_property
from imbue_core.cattrs_serialization import serialize_to_json
from imbue_core.fixed_traceback import FixedTraceback
from imbue_core.frozen_utils import FrozenDict
from imbue_core.frozen_utils import FrozenMapping
from imbue_core.pydantic_serialization import SerializableModel

@attr.s(auto_attribs=True, frozen=True)
class A:
    thing_one: str
    thing_two: Mapping[str, str]


def test_javascript_style_serialization() -> None:
    a1 = A(thing_one="1", thing_two={"dont_camelize": "2"})
    a2 = A(thing_one="1", thing_two={"dont_camelize": "2"})
    expected_json_notfrozen = (
        """{"__type": "imbue_core.cattrs_serialization_test.A", "thingOne": "1", "thingTwo": {"dont_camelize": "2"}}"""
    )
    expected_json_frozen = (
        """{"__type": "imbue_core.cattrs_serialization_test.A", "thingOne": "1", "thingTwo": {"dont_camelize": "2"}}"""
    )
    assert serialize_to_json(a1, sort_keys=True, for_javascript=True) == expected_json_notfrozen
    assert serialize_to_json(a2, sort_keys=True, for_javascript=True) == expected_json_frozen


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class Pet:
    z: int


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class Dog(Pet):
    pass


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class Pets:
    x: tuple[Pet]
    y: int


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class Human:
    z: int


def test_type_checking_in_deserialization() -> None:
    # This should not raise an exception, since a Dog is a Pet
    deserialize_from_json(
        '[{"x": [{"z": 2, "__type": "imbue_core.cattrs_serialization_test.Dog"}], "y": 2, "__type": "imbue_core.cattrs_serialization_test.Pets"}]'
    )

    # This should raise an exception, since a Human is not a Pet.
    with pytest.raises(SerializationError):
        deserialize_from_json(
            '[{"x": [{"z": 2, "__type": "imbue_core.cattrs_serialization_test.Human"}], "y": 2, "__type": "imbue_core.cattrs_serialization_test.A"}]'
        )


@attr.s(auto_attribs=True)
class ForwardRefClass:
    x: dict[str, "ForwardRefClass"]


def test_can_handle_forward_refs() -> None:
    x = ForwardRefClass(x={"a": ForwardRefClass(x={})})
    j = serialize_to_json(x, sort_keys=True)
    assert (
        j
        == """{"__type": "imbue_core.cattrs_serialization_test.ForwardRefClass", "x": {"__entries": [["a", {"__type": "imbue_core.cattrs_serialization_test.ForwardRefClass", "x": {"__entries": [], "__type": "builtins.dict"}}]], "__type": "builtins.dict"}}"""
    )
    deserialized = deserialize_from_json(j)
    assert isinstance(deserialized.x["a"], ForwardRefClass)


@attr.s(auto_attribs=True, frozen=True)
class ThingWithLiteral:
    x: Literal["hello"]


def test_works_with_literal() -> None:
    obj = ThingWithLiteral(x="hello")
    assert deserialize_from_json(serialize_to_json(obj)) == obj


@attr.s(auto_attribs=True, frozen=True)
class ThingWithUnion:
    x: int | Literal["hello"]


def test_works_with_union() -> None:
    obj = ThingWithUnion(x="hello")
    assert deserialize_from_json(serialize_to_json(obj)) == obj


def test_mapping() -> None:
    x: Mapping[str, int] = {"a": 1, "b": 2}
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert serialized_x == """{"__entries": [["a", 1], ["b", 2]], "__type": "builtins.dict"}"""
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True)
class ClassWithMapping:
    t: FrozenMapping[Path, Path]


def test_class_with_mapping() -> None:
    x = ClassWithMapping(t=FrozenDict({Path("a"): Path("b")}))
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithMapping", "t": {"__entries": [[{"__type": "pathlib.PosixPath", "value": "a"}, {"__type": "pathlib.PosixPath", "value": "b"}]], "__type": "imbue_core.frozen_utils.FrozenDict"}}"""
    )
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True)
class ClassWithFrozenSet:
    t: frozenset


def test_frozenset() -> None:
    x = ClassWithFrozenSet(t=frozenset([1, 23, 4]))
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithFrozenSet", "t": {"__type": "builtins.frozenset", "value": [1, 4, 23]}}"""
    )
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True)
class ClassWithUUID:
    t: UUID


def test_uuid() -> None:
    x = ClassWithUUID(t=UUID("999e6c58713211ef816a00155dfef5ed"))
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithUUID", "t": {"__type": "uuid.UUID", "value": "999e6c58713211ef816a00155dfef5ed"}}"""
    )
    assert x == deserialize_from_json(serialized_x)


def test_tuples() -> None:
    example = {"examples": (1, 2, 3)}
    serialized = serialize_to_json(example)
    assert (
        serialized
        == '{"__type": "builtins.dict", "__entries": [["examples", {"value": [1, 2, 3], "__type": "builtins.tuple"}]]}'
    )
    assert example == deserialize_from_json(serialized)


@attr.s(auto_attribs=True)
class ClassWithTraceback:
    t: FixedTraceback


def test_traceback() -> None:
    try:
        raise Exception
    except Exception as e:
        traceback = FixedTraceback.from_tb(getattr(e, "__traceback__", None))  # type: ignore
        x = ClassWithTraceback(t=traceback)
        serialized_x = serialize_to_json(x, sort_keys=True)
        serialized_then_deserialized_then_serialized_x = serialize_to_json(
            deserialize_from_json(serialized_x), sort_keys=True
        )
        assert serialized_x == serialized_then_deserialized_then_serialized_x


@attr.s(auto_attribs=True)
class ClassWithDatetime:
    t: datetime.datetime


def test_datetime() -> None:
    x = ClassWithDatetime(t=datetime.datetime(2021, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc))
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithDatetime", "t": {"__type": "datetime.datetime", "time": 1609459200.0, "tzaware": true}}"""
    )
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True)
class ClassWithCachedSerializableProperties:
    n: int

    @cached_serializable_property
    def x(self) -> int:
        return self.n

    @property
    def should_not_be_serialized(self) -> int:
        return 2


def test_cached_serializable_properties() -> None:
    init_n = 1
    x = ClassWithCachedSerializableProperties(n=init_n)
    cached_n = x.n

    # Check that the property is cache
    serialized_x = serialize_to_json(x, sort_keys=True, for_javascript=True)
    assert (
        serialized_x
        == f"""{{"__type": "imbue_core.cattrs_serialization_test.ClassWithCachedSerializableProperties", "n": {init_n}, "x": {cached_n}}}"""
    )
    assert x == deserialize_from_json(serialized_x)

    # Increment n and check that the property is not incremented again (it should use the initial cached value)
    x.n = init_n + 1
    serialized_x = serialize_to_json(x, sort_keys=True, for_javascript=True)
    assert (
        serialized_x
        == f"""{{"__type": "imbue_core.cattrs_serialization_test.ClassWithCachedSerializableProperties", "n": {init_n + 1}, "x": {cached_n}}}"""
    )


@attr.s(auto_attribs=True)
class ClassWithSerializableProperties:
    n: int

    @serializable_property
    def x(self) -> int:
        return self.n

    @property
    def should_not_be_serialized(self) -> int:
        return 2


def test_serializable_properties() -> None:
    n = 1
    x = ClassWithSerializableProperties(n=n)
    serialized_x = serialize_to_json(x, sort_keys=True, for_javascript=True)
    assert (
        serialized_x
        == f"""{{"__type": "imbue_core.cattrs_serialization_test.ClassWithSerializableProperties", "n": {n}, "x": {n}}}"""
    )
    assert x == deserialize_from_json(serialized_x)

    # Check that the property is incremented (i.e. serialized property is computed again)
    n += 1
    x.n = n
    serialized_x = serialize_to_json(x, sort_keys=True, for_javascript=True)
    assert (
        serialized_x
        == f"""{{"__type": "imbue_core.cattrs_serialization_test.ClassWithSerializableProperties", "n": {n}, "x": {n}}}"""
    )
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class Subclass:
    bar: str


SubclassT = TypeVar("SubclassT", bound=Subclass)


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class GenericAttrsClass(Generic[SubclassT]):
    foo: SubclassT


def test_generic_attrs_class() -> None:
    instance = GenericAttrsClass(foo=Subclass(bar="bar"))
    serialized = serialize_to_json(instance)
    assert instance == deserialize_from_json(serialized)


class Animal(StrEnum):
    DOG = "DOG"
    CAT = "CAT"


def test_str_enum() -> None:
    x = Animal.DOG
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert serialized_x == '"DOG"'
    assert x == deserialize_from_json(serialized_x)


class Toys(IntEnum):
    BALL = 1
    FRISBEE = 2


def test_int_enum() -> None:
    x = Toys.BALL
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert serialized_x == "1"
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True)
class ClassWithEnum:
    t: Animal
    mapping: Mapping[Animal, Animal]


def test_class_with_enum() -> None:
    x = ClassWithEnum(t=Animal.DOG, mapping={Animal.DOG: Animal.CAT})
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithEnum", "mapping": {"__entries": [["DOG", "CAT"]], "__type": "builtins.dict"}, "t": "DOG"}"""
    )
    assert x == deserialize_from_json(serialized_x)


def test_dict_complex_keys() -> None:
    d = {Path("a"): 1}
    serialized_d = serialize_to_json(d, sort_keys=True)
    assert (
        serialized_d
        == """{"__entries": [[{"__type": "pathlib.PosixPath", "value": "a"}, 1]], "__type": "builtins.dict"}"""
    )
    assert d == deserialize_from_json(serialized_d)


@attr.s(auto_attribs=True)
class ClassWithMarkedNotToSerializeAttributes:
    x: str
    y: str = attr.field(metadata=DONT_SERIALIZE)


def test_dont_serialize_field() -> None:
    x = ClassWithMarkedNotToSerializeAttributes(x="hello", y="world")
    # When serializing, we don't include the field that is marked to not be serialized.
    serialized_x = serialize_to_json(x, is_reversible=False, exclude_dont_serialize_fields=True)
    assert serialized_x == """{"x": "hello"}"""

    # We can optionally choose to ignore do no serialize flags (useful for cases when serializing to disk,
    #  as opposed to sending data over the network)
    serialized_x = serialize_to_json(x, is_reversible=True, exclude_dont_serialize_fields=False)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithMarkedNotToSerializeAttributes", "x": "hello", "y": "world"}"""
    )
    assert x == deserialize_from_json(serialized_x)

    # Check we get error when serializing with do not serialize fields, but set is_reversible to True
    with pytest.raises(SerializationError):
        serialize_to_json(x, is_reversible=True, exclude_dont_serialize_fields=True)


@attr.s(auto_attribs=True)
class ClassWithNestedMarkedNotToSerializeAttributes:
    a: str
    b: ClassWithMarkedNotToSerializeAttributes


def test_dont_serialize_field_in_nested_class() -> None:
    x = ClassWithMarkedNotToSerializeAttributes(x="hello", y="world")
    y = ClassWithNestedMarkedNotToSerializeAttributes(a="fooshie", b=x)
    # # When serializing, we don't include the field that is marked to not be serialized.
    serialized_y = serialize_to_json(y, is_reversible=False, exclude_dont_serialize_fields=True)
    assert serialized_y == """{"a": "fooshie", "b": {"x": "hello"}}"""

    # We can optionally choose to ignore do no serialize flags (useful for cases when serializing to disk,
    #  as opposed to sending data over the network)
    serialized_y = serialize_to_json(y, is_reversible=True, exclude_dont_serialize_fields=False)

    assert (
        serialized_y
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithNestedMarkedNotToSerializeAttributes", "a": "fooshie", "b": {"__type": "imbue_core.cattrs_serialization_test.ClassWithMarkedNotToSerializeAttributes", "x": "hello", "y": "world"}}"""
    )
    assert y == deserialize_from_json(serialized_y)


@attr.s(auto_attribs=True)
class RecursiveClassWithDoNotSerializeAttributes:
    x: str
    y: Optional["RecursiveClassWithDoNotSerializeAttributes"] = attr.field(metadata=DONT_SERIALIZE)


def test_recursive_class_with_dont_serialize_attributes() -> None:
    obj1 = RecursiveClassWithDoNotSerializeAttributes(x="hello", y=None)
    obj2 = RecursiveClassWithDoNotSerializeAttributes(x="world", y=obj1)
    obj1.y = obj2

    with pytest.raises(SerializationError):
        serialize_to_json(obj1, sort_keys=True, exclude_dont_serialize_fields=False)

    serialized_obj1 = serialize_to_json(obj1, sort_keys=True, is_reversible=False, exclude_dont_serialize_fields=True)
    assert serialized_obj1 == """{"x": "hello"}"""


@attr.s(auto_attribs=True)
class ClassWithAnyioPath:
    my_path: anyio.Path


def test_anyio_path() -> None:
    x = ClassWithAnyioPath(my_path=anyio.Path("a"))
    serialized_x = serialize_to_json(x, sort_keys=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithAnyioPath", "my_path": {"__type": "anyio.Path", "value": "a"}}"""
    )
    assert x == deserialize_from_json(serialized_x)


@attr.s(auto_attribs=True)
class ClassWithAsyncioObjects:
    lock: asyncio.Lock = asyncio.Lock()
    event: asyncio.Event = asyncio.Event()


def test_defaults_for_async_objects() -> None:
    x = ClassWithAsyncioObjects()
    serialized_x = serialize_to_json(x, sort_keys=True, use_defaults_for_unserializable_fields=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithAsyncioObjects", "event": null, "lock": null}"""
    )
    deserialized_x = deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=True)
    assert isinstance(deserialized_x.lock, asyncio.Lock)
    assert deserialized_x.event is None
    with pytest.raises(SerializationError):
        serialize_to_json(x, sort_keys=True, use_defaults_for_unserializable_fields=False)


@attr.s(auto_attribs=True)
class ClassWithSpecialMappingType:
    cache: LRUCache = LRUCache(maxsize=10)


def test_defaults_for_special_mapping_types() -> None:
    # NOTE: this asserts the current behavior for special mapping types; the expected output
    # below must be updated if mapping serialization changes.
    x = ClassWithSpecialMappingType()
    serialized_x = serialize_to_json(x, sort_keys=True, use_defaults_for_unserializable_fields=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithSpecialMappingType", "cache": {"__entries": [], "__type": "cachetools.LRUCache"}}"""
    )
    deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=True)


@attr.s(auto_attribs=True)
class SomeAttrsClass:
    x: int
    y: str = attr.ib(default="abc", metadata=SERIALIZE_WITH_DEFAULT)
    z: list[int] = attr.ib(factory=list, metadata=SERIALIZE_WITH_DEFAULT)


@attr.s(auto_attribs=True)
class ClassWithUnserializableFields:
    obj1: SomeAttrsClass
    obj2: SomeAttrsClass = attr.ib(metadata=SERIALIZE_WITH_DEFAULT)


def test_skipping_serialization_for_marked_fields() -> None:
    x = ClassWithUnserializableFields(
        obj1=SomeAttrsClass(x=1, y="hello", z=[1, 2, 3]), obj2=SomeAttrsClass(x=2, y="hello")
    )
    serialized_x = serialize_to_json(x, sort_keys=True, use_defaults_for_unserializable_fields=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ClassWithUnserializableFields", "obj1": {"__type": "imbue_core.cattrs_serialization_test.SomeAttrsClass", "x": 1, "y": "abc", "z": []}, "obj2": null}"""
    )
    deserialized_x = deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=True)
    assert isinstance(deserialized_x.obj1, SomeAttrsClass)
    assert deserialized_x.obj1.x == 1
    assert deserialized_x.obj1.y == "abc"
    assert deserialized_x.obj1.z == []
    assert deserialized_x.obj2 is None


@attr.s(auto_attribs=True)
class BaseClass:
    pass


@attr.s(auto_attribs=True)
class CollectionOfObjectsClass:
    collection: tuple[BaseClass, ...] = attr.ib(factory=tuple)


@attr.s(auto_attribs=True)
class ChildClassWithPotentialCircularReference(BaseClass):
    obj: CollectionOfObjectsClass = attr.ib(metadata=SERIALIZE_WITH_DEFAULT)


def test_defaults_for_unserializable_fields_circular_reference() -> None:
    x = ChildClassWithPotentialCircularReference(obj=CollectionOfObjectsClass())
    x.obj.collection = (x,)
    serialized_x = serialize_to_json(x, sort_keys=True, use_defaults_for_unserializable_fields=True)
    assert (
        serialized_x
        == """{"__type": "imbue_core.cattrs_serialization_test.ChildClassWithPotentialCircularReference", "obj": null}"""
    )
    deserialized_x = deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=True)
    assert deserialized_x.obj is None

    with pytest.raises(SerializationError):
        serialize_to_json(x, sort_keys=True, use_defaults_for_unserializable_fields=False)


class PydanticSettingsClass(BaseSettings):
    model_config = SettingsConfigDict(**SerializableModel.model_config)

    test_path: Path = Path("/tmp/asdf")
    command: str
    name: str | None = None
    is_primary: bool = False
    is_terminal_expanded: bool | None = True

    @cached_property
    def default_name(self) -> str:
        return "default"


class PydanticNestedSettings(BaseSettings):
    model_config = SettingsConfigDict(**SerializableModel.model_config)

    more_tests: int = 42
    nested_field: PydanticSettingsClass


def test_pydantic_for_frontend() -> None:
    x = PydanticSettingsClass(
        command="hello world!",
        name="named",
        is_primary=False,
        is_terminal_expanded=None,
    )

    expected_serialized_x = """{"testPath": "/tmp/asdf", "command": "hello world!", "name": "named", "isPrimary": false, "isTerminalExpanded": null}"""
    serialized_x = serialize_to_json(x, is_reversible=False, for_javascript=True, exclude_dont_serialize_fields=True)
    assert serialized_x == expected_serialized_x


def test_nested_pydantic_for_frontend() -> None:
    x = PydanticNestedSettings(
        nested_field=PydanticSettingsClass(
            command="hello world!", name="named", is_primary=False, is_terminal_expanded=None
        )
    )

    expected_serialized_x = """{"moreTests": 42, "nestedField": {"testPath": "/tmp/asdf", "command": "hello world!", "name": "named", "isPrimary": false, "isTerminalExpanded": null}}"""
    serialized_x = serialize_to_json(x, is_reversible=False, for_javascript=True, exclude_dont_serialize_fields=True)
    assert serialized_x == expected_serialized_x


def test_pydantic_serdes() -> None:
    x = PydanticSettingsClass(command="hello world!", name="named", is_primary=False, is_terminal_expanded=None)

    expected_serialized_x = """{"__type": "imbue_core.cattrs_serialization_test.PydanticSettingsClass", "test_path": "/tmp/asdf", "command": "hello world!", "name": "named", "is_primary": false, "is_terminal_expanded": null}"""
    serialized_x = serialize_to_json(
        x,
        is_reversible=True,
    )
    assert serialized_x == expected_serialized_x

    deserialized_x = deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=True)
    assert deserialized_x == x


def test_nested_pydantic_serdes() -> None:
    x = PydanticNestedSettings(
        nested_field=PydanticSettingsClass(
            command="hello world!", name="named", is_primary=False, is_terminal_expanded=None
        ),
    )

    # Access the property to make sure it's not added to the serialization
    assert x.nested_field.default_name == "default"

    expected_serialized_x = """{"__type": "imbue_core.cattrs_serialization_test.PydanticNestedSettings", "more_tests": 42, "nested_field": {"test_path": "/tmp/asdf", "command": "hello world!", "name": "named", "is_primary": false, "is_terminal_expanded": null}}"""
    serialized_x = serialize_to_json(
        x,
        is_reversible=True,
    )
    assert serialized_x == expected_serialized_x

    deserialized_x = deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=False)
    assert deserialized_x == x


class FakeException(Exception):
    fake_attr: str
    fake_attr2: str

    def __init__(self, attr1: str, attr2: str) -> None:
        self.fake_attr = attr1
        self.fake_attr2 = attr2


def test_serialization_for_exceptions() -> None:
    error_types_and_args = {
        FakeException: ["fake_attr1", "fake_attr2"],
        TypeError: ["incorrect_type"],
        SerializationError: ["bad serialization"],
    }
    for error_type, args in error_types_and_args.items():
        try:
            raise error_type(*args)
        except BaseException as e:
            serialized_e = serialize_to_json(e, sort_keys=True)
            deserialized_e = deserialize_from_json(serialized_e)
            assert isinstance(deserialized_e, SerializedException)
            e_args = deserialized_e.args
            assert isinstance(e_args, tuple)
            assert set(e_args) == set(args)
            assert deserialized_e.exception_class == error_type


@attr.s(auto_attribs=True)
class AttrException(Exception):
    attr1: str
    attr2: str


def test_attr_exception() -> None:
    x = AttrException("attr1", "attr2")
    expected_serialized_x = (
        '{"__type": "imbue_core.cattrs_serialization_test.AttrException", "attr1": "attr1", "attr2": "attr2"}'
    )

    serialized_x = serialize_to_json(x)
    assert serialized_x == expected_serialized_x
    deserialized_x = deserialize_from_json(serialized_x)
    assert isinstance(deserialized_x, AttrException)
    assert deserialized_x.attr1 == "attr1"
    assert deserialized_x.attr2 == "attr2"

    serialized_x = serialize_to_json(x, use_defaults_for_unserializable_fields=True)
    assert serialized_x == expected_serialized_x
    deserialized_x = deserialize_from_json(serialized_x, use_defaults_for_unserializable_fields=True)
    assert isinstance(deserialized_x, AttrException)
    assert deserialized_x.attr1 == "attr1"
    assert deserialized_x.attr2 == "attr2"


def test_bytes_serialization() -> None:
    """Test that bytes are properly serialized and deserialized."""
    # Test basic bytes serialization
    test_bytes = b"hello world"
    serialized = serialize_to_json(test_bytes)
    expected_value = base64.b64encode(test_bytes).decode("ascii")
    expected = f'{{"__type": "builtins.bytes", "value": "{expected_value}"}}'
    assert serialized == expected

    # Test deserialization
    deserialized = deserialize_from_json(serialized)
    assert isinstance(deserialized, bytes)
    assert deserialized == test_bytes

    # Test empty bytes
    empty_bytes = b""
    serialized_empty = serialize_to_json(empty_bytes)
    expected_value = base64.b64encode(empty_bytes).decode("ascii")
    expected_empty = f'{{"__type": "builtins.bytes", "value": "{expected_value}"}}'
    assert serialized_empty == expected_empty
    deserialized_empty = deserialize_from_json(serialized_empty)
    assert isinstance(deserialized_empty, bytes)
    assert deserialized_empty == empty_bytes

    # Test bytes with special characters
    special_bytes = b"\x00\x01\xff\xfe"
    serialized_special = serialize_to_json(special_bytes)
    expected_value = base64.b64encode(special_bytes).decode("ascii")
    expected_special = f'{{"__type": "builtins.bytes", "value": "{expected_value}"}}'
    assert serialized_special == expected_special
    deserialized_special = deserialize_from_json(serialized_special)
    assert isinstance(deserialized_special, bytes)
    assert deserialized_special == special_bytes


@attr.s(auto_attribs=True)
class ClassWithBytes:
    data: bytes
    name: str


def test_class_with_bytes_serialization() -> None:
    """Test serialization of a class containing bytes."""
    obj = ClassWithBytes(data=b"binary data", name="test")
    serialized = serialize_to_json(obj)
    expected_data_value = base64.b64encode(obj.data).decode("ascii")
    expected = f'{{"__type": "imbue_core.cattrs_serialization_test.ClassWithBytes", "data": {{"__type": "builtins.bytes", "value": "{expected_data_value}"}}, "name": "test"}}'
    assert serialized == expected

    deserialized = deserialize_from_json(serialized)
    assert isinstance(deserialized, ClassWithBytes)
    assert deserialized.data == b"binary data"
    assert deserialized.name == "test"


class PydanticSettingsWithHttpUrl(BaseSettings):
    url: HttpUrl


def test_pydantic_with_http_url() -> None:
    object_ = PydanticSettingsWithHttpUrl(url=HttpUrl("https://imbue.com"))
    expected_serialized = (
        '{"__type": "imbue_core.cattrs_serialization_test.PydanticSettingsWithHttpUrl", "url": "https://imbue.com/"}'
    )
    assert serialize_to_json(object_) == expected_serialized
    deserialized = deserialize_from_json(expected_serialized)
    assert object_ == deserialized
