import asyncio
import functools
import threading
from contextlib import AbstractAsyncContextManager
from contextlib import contextmanager
from typing import Any
from typing import AsyncGenerator
from typing import Awaitable
from typing import Callable
from typing import Coroutine
from typing import Generator
from typing import Generic
from typing import ParamSpec
from typing import TypeVar
from typing import cast

from imbue_core.async_monkey_patches import safe_cancel

P = ParamSpec("P")
R = TypeVar("R")
S = TypeVar("S")


def sync(func: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    """Decorator that runs an async function synchronously by dispatching to
    an event loop running in a separate thread.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        loop = _get_or_create_event_loop()
        return asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop).result()

    return wrapper


def sync_generator(func: Callable[P, AsyncGenerator[R, None]]) -> Callable[P, Generator[R, None, None]]:
    """Decorator that runs an async generator synchronously by dispatching to
    an event loop running in a separate thread.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Generator[R, None, None]:
        loop = _get_or_create_event_loop()
        agen = func(*args, **kwargs)
        while True:
            try:
                future = asyncio.run_coroutine_threadsafe(agen.__anext__(), loop)
                yield future.result()
            except StopAsyncIteration:
                break

    return wrapper


@contextmanager
# pyre-ignore[24]: pyre doesn't understand AbstractAsyncContextManager
def sync_contextmanager(async_context_manager: AbstractAsyncContextManager[S]) -> Generator[S, None, None]:
    sync_aenter = sync(async_context_manager.__aenter__)
    sync_aexit = sync(async_context_manager.__aexit__)

    enter_result = sync_aenter()
    try:
        yield enter_result
    except BaseException as e:
        if not sync_aexit(e.__class__, e, e.__traceback__):
            raise
    else:
        sync_aexit(None, None, None)


_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK: threading.Lock = threading.Lock()


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is not None:
        return _LOOP
    with _LOOP_LOCK:
        # Check again in case another thread created the loop while we were waiting for the lock.
        if _LOOP is not None:
            return _LOOP
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
        # pyre-ignore[16]: we have _LOOP_LOCK, so _LOOP is still not None
        threading.Thread(target=_LOOP.run_forever, daemon=True, name="async_loop").start()
    return _LOOP  # pyre-ignore[7]: we just made _LOOP, so it's not None unless it got destroyed just now


_NOT_FOUND = object()

T = TypeVar("T")


class AsyncCachedProperty(Generic[T]):
    """A descriptor factory that behaves very similarly to `functools.cached_property`, but for
    async methods.

    The type annotations here are rough; it's not realistic to get them perfect without using a .pyi file.
    """

    def __init__(self, func: Callable[[Any], Coroutine[None, None, T]]) -> None:
        self.func = func
        self.attrname: str | None = None
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        if self.attrname is None:
            self.attrname = name
        elif name != self.attrname:
            raise TypeError("Cannot assign the same AsyncCachedProperty to multiple names")

    def _get_attrname(self) -> str:
        if self.attrname is None:
            raise TypeError("Cannot use AsyncCachedProperty instance without calling __set_name__")
        return self.attrname

    def _get_cache(self, instance: object) -> dict[str, Any]:
        try:
            return instance.__dict__
        except AttributeError:
            raise TypeError(
                "Cannot use AsyncCachedProperty with instances that do not have a __dict__ attribute"
            ) from None

    def __get__(self, instance: object, owner: type | None = None) -> Awaitable[T]:
        if instance is None:
            return self  # type: ignore
        attrname = self._get_attrname()
        cache = self._get_cache(instance)
        val = cache.get(attrname, _NOT_FOUND)
        if val is not _NOT_FOUND:
            return cast(Awaitable[T], val)

        task = asyncio.create_task(self.func(instance))
        cache[attrname] = task
        return task

    def __delete__(self, instance: object) -> None:
        if instance is None:
            raise TypeError("Cannot delete AsyncCachedProperty on a class")
        attrname = self._get_attrname()
        cache = self._get_cache(instance)
        try:
            awaitable = cache.pop(attrname)
            if not awaitable.done():
                safe_cancel(awaitable)
        except KeyError:
            raise AttributeError(f"Cannot delete attribute {self.attrname!r}") from None

    def __set__(self, instance: object, value: T) -> None:
        if instance is None:
            raise TypeError("Cannot set AsyncCachedProperty on a class")
        attrname = self._get_attrname()
        cache = self._get_cache(instance)
        existing = cache.pop(attrname, None)
        if existing is not None and not existing.done():
            safe_cancel(existing)
        fut: asyncio.Future[T] = asyncio.Future()
        fut.set_result(value)
        cache[attrname] = fut
