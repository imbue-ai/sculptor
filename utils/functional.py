import itertools
import threading
from functools import lru_cache
from typing import Any
from typing import Callable
from typing import Iterable
from typing import ParamSpec
from typing import Protocol
from typing import TypeVar

T = TypeVar("T")

P = ParamSpec("P")
R = TypeVar("R")


class _SupportsLessThan(Protocol):
    def __lt__(self, __other: Any) -> bool: ...


TK = TypeVar("TK", bound=_SupportsLessThan)
TV = TypeVar("TV")


def first(iterable: Iterable[T]) -> T | None:
    return next(iter(iterable), None)


def group_by_helper(data: Iterable[TV], get_key: Callable[[TV], TK]) -> dict[TK, list[TV]]:
    data = sorted(data, key=get_key)
    return {k: list(g) for k, g in itertools.groupby(data, get_key)}


def cached_and_locked(func: Callable[P, R], maxsize: int = 1) -> Callable[P, R]:
    """Cache the result of a function and ensure that it is thread-safe."""
    lock = threading.Lock()
    # pyre-ignore[6]:
    # Typeshed uses Callable[..., R] in the type signature of lru_cache,
    # and Pyre complains that Callable[P, R] is not a subtype of Callable[..., T],
    # which seems wrong.
    # Most likely, Pyre's support for ParamSpec is incomplete.
    cached_func = lru_cache(maxsize=maxsize)(func)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with lock:
            return cached_func(*args, **kwargs)

    return wrapper
