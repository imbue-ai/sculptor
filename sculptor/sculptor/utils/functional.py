from typing import Iterable
from typing import TypeVar

T = TypeVar("T")


def first(iterable: Iterable[T]) -> T | None:
    return next(iter(iterable), None)
