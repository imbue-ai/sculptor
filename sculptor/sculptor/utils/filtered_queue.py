from collections.abc import Callable
from queue import Queue
from typing import TypeVar

_ItemT = TypeVar("_ItemT")


class FilteredQueue(Queue[_ItemT]):
    """A queue that silently drops items rejected by a predicate when they are enqueued."""

    def __init__(self, is_allowed_fn: Callable[[_ItemT], bool], maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._is_allowed_fn = is_allowed_fn

    def put(self, item: _ItemT, block: bool = True, timeout: float | None = None) -> None:
        if not self._is_allowed_fn(item):
            return
        super().put(item, block, timeout)

    def put_nowait(self, item: _ItemT) -> None:
        if not self._is_allowed_fn(item):
            return
        super().put_nowait(item)
