from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def first(iterable: Iterable[T]) -> T | None:
    """Return the first item of an iterable, or None if it is empty."""
    return next(iter(iterable), None)
