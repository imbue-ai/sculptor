import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import attr
import pytest

from imbue_core.async_utils import AsyncCachedProperty
from imbue_core.async_utils import sync_contextmanager
from imbue_core.async_utils import sync_generator


@pytest.mark.asyncio
async def test_async_cached_property() -> None:
    class Foo:
        def __init__(self) -> None:
            self.called_times = 0

        @AsyncCachedProperty
        async def bar(self) -> int:
            self.called_times += 1
            return 42

    foo = Foo()
    assert await foo.bar == 42
    assert await foo.bar == 42
    assert foo.called_times == 1


@pytest.mark.asyncio
async def test_clear_cached_property() -> None:
    class Foo:
        def __init__(self) -> None:
            self.called_times = 0

        @AsyncCachedProperty
        async def bar(self) -> int:
            self.called_times += 1
            return 42

    foo = Foo()
    assert await foo.bar == 42
    assert await foo.bar == 42
    assert foo.called_times == 1
    del foo.bar
    assert await foo.bar == 42
    assert foo.called_times == 2


async def returns1() -> int:
    return 1


@pytest.mark.asyncio
async def test_async_cached_property_set() -> None:
    class Foo:
        def __init__(self) -> None:
            self.called_times = 0

        @AsyncCachedProperty
        async def bar(self) -> int:
            self.called_times += 1
            return 42

    foo = Foo()
    foo.bar = 1

    assert await foo.bar == 1
    assert await foo.bar == 1
    assert foo.called_times == 0

    del foo.bar
    assert await foo.bar == 42
    assert foo.called_times == 1


@pytest.mark.asyncio
async def test_async_cached_property_on_frozen_attrs_class() -> None:
    @attr.s(auto_attribs=True, frozen=True)
    class Foo:
        x: int

        @AsyncCachedProperty
        async def bar(self) -> int:
            return self.x + 1

    foo = Foo(41)
    assert await foo.bar == 42
    assert await foo.bar == 42


@pytest.mark.asyncio
async def test_async_cached_property_concurrent() -> None:
    """Tests that the property is only computed once when accessed concurrently
    during the first computation."""

    class Foo:
        def __init__(self, in_bar_event: asyncio.Event, finish_bar_event: asyncio.Event) -> None:
            self._in_bar_event = in_bar_event
            self._finish_bar_event = finish_bar_event
            self.called_times = 0

        @AsyncCachedProperty
        async def bar(self) -> int:
            self.called_times += 1
            self._in_bar_event.set()
            await self._finish_bar_event.wait()
            return 42

    in_bar_event = asyncio.Event()
    finish_bar_event = asyncio.Event()
    foo = Foo(in_bar_event, finish_bar_event)

    async def bar() -> int:
        return await foo.bar

    task1 = asyncio.create_task(bar())
    task2 = asyncio.create_task(bar())

    await in_bar_event.wait()
    assert foo.called_times == 1
    finish_bar_event.set()
    r1, r2 = await asyncio.gather(task1, task2)
    assert r1 == 42
    assert r2 == 42
    assert foo.called_times == 1


def test_sync_contextmanager() -> None:
    state = []

    @asynccontextmanager
    async def async_contextmanager() -> AsyncGenerator[int, None]:
        state.append(1)
        await asyncio.sleep(0)
        try:
            yield 5
        except AssertionError:
            state.append(2)
        else:
            state.append(3)

    with sync_contextmanager(async_contextmanager()) as value:
        pass

    assert value == 5
    assert state == [1, 3]

    del value
    state = []

    with sync_contextmanager(async_contextmanager()) as value:
        raise AssertionError

    assert value == 5
    assert state == [1, 2]

    del value
    state = []
    with pytest.raises(ValueError):
        with sync_contextmanager(async_contextmanager()) as value:
            raise ValueError

    assert value == 5
    assert state == [1]


def test_sync_generator() -> None:
    async def agen(x: int, *, y: int) -> AsyncGenerator[int, None]:
        yield x
        yield y
        yield x + y

    a, b = 1, 2
    result = list(sync_generator(agen)(a, y=b))
    assert result == [a, b, a + b]


def test_sync_generator_decorator() -> None:
    @sync_generator
    async def agen(x: int, *, y: int) -> AsyncGenerator[int, None]:
        yield x
        yield y
        yield x + y

    a, b = 1, 2
    result = list(agen(a, y=b))
    assert result == [a, b, a + b]


def test_sync_generator_exception() -> None:
    @sync_generator
    async def agen() -> AsyncGenerator[int, None]:
        yield 1
        raise ValueError("test")

    with pytest.raises(ValueError, match="test"):
        list(agen())
