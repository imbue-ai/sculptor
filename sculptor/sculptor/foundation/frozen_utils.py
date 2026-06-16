from abc import ABC
from abc import abstractmethod
from copy import deepcopy
from functools import cached_property
from typing import Any
from typing import Iterable
from typing import Mapping
from typing import NoReturn
from typing import Protocol
from typing import TYPE_CHECKING
from typing import TypeAlias
from typing import TypeVar

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem


class _SupportsLessThan(Protocol):
    def __lt__(self, __other: Any) -> bool: ...


T = TypeVar("T")
TV = TypeVar("TV")
TK = TypeVar("TK", bound=_SupportsLessThan)


class FrozenMapping(Mapping[T, TV], ABC):
    @abstractmethod
    def __hash__(self) -> int: ...


class FrozenDict(dict[T, TV], FrozenMapping[T, TV]):
    def _key(self) -> frozenset[tuple[T, TV]]:
        return frozenset(self.items())

    @cached_property
    def _hash(self) -> int:
        # hashing the frozenset of items is fine
        return hash(self._key())

    def __hash__(self) -> int:  # type: ignore
        return self._hash

    def _mutation_error(self, method: str) -> RuntimeError:
        return RuntimeError(f"Cannot call mutation method {method} on _FrozenDict {self}")

    def __setitem__(self, __name: T, __value: TV) -> NoReturn:
        raise self._mutation_error("__setitem__")

    def __delitem__(self, __name: T) -> NoReturn:
        raise self._mutation_error("__delitem__")

    # pyre-fixme[14]: pyre thinks this is an inconsistent override and i don't feel like fixing it because the function ignores its arguments
    def update(self, __m: "SupportsKeysAndGetItem[T, TV] | Iterable[tuple[T, TV]]" = (), **kwargs: TV) -> NoReturn:
        raise self._mutation_error("update")

    # pyre-fixme[14]: pyre thinks this is an inconsistent override and i don't feel like fixing it because the function ignores its arguments
    def setdefault(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise self._mutation_error("setdefault")

    # pyre-fixme[14]: pyre thinks this is an inconsistent override and i don't feel like fixing it because the function ignores its arguments
    def pop(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise self._mutation_error("pop")

    # pyre-ignore[15]: pyre doesn't like overriding the return type with NoReturn
    def popitem(self) -> NoReturn:
        raise self._mutation_error("popitem")

    # pyre-ignore[15]: pyre doesn't like overriding the return type with NoReturn
    def clear(self) -> NoReturn:
        raise self._mutation_error("clear")

    def __repr__(self) -> str:
        return f"_FrozenDict({super().__repr__()})"

    def __copy__(self) -> "FrozenDict":
        return type(self)(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> "FrozenDict":
        memo[id(self)] = self
        copied_items = ((deepcopy(key, memo), deepcopy(value, memo)) for key, value in self.items())
        return type(self)(copied_items)

    def __reduce__(self) -> tuple[Any, ...]:
        return (FrozenDict, (dict(self),))


def empty_mapping() -> FrozenDict[Any, Any]:
    return FrozenDict()


# Recursive type alias that captures the possible types of JSON objects (e.g. from json.loads).
JSON: TypeAlias = "str | int | bool | float | None | dict[str, JSON] | list[JSON]"


# Immutable version of JSON.
FrozenJSON: TypeAlias = "str | int | bool | float | None | FrozenDict[str, FrozenJSON] | tuple[FrozenJSON, ...]"


def deep_freeze_json(json: JSON) -> FrozenJSON:
    if isinstance(json, dict):
        return FrozenDict({k: deep_freeze_json(v) for k, v in json.items()})
    elif isinstance(json, list):
        return tuple(deep_freeze_json(v) for v in json)
    else:
        return json
