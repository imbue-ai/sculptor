from typing import Callable

from imbue_core.function_utils import sequence_callbacks


def test_sequence_callbacks_no_callbacks() -> None:
    combined = sequence_callbacks()
    # Should not raise when called
    combined(1, 2, 3)


def test_sequence_callbacks_single_callback() -> None:
    results: list[int] = []

    def callback(x: int) -> None:
        results.append(x)

    combined = sequence_callbacks(callback)
    combined(42)

    assert results == [42]


def test_sequence_callbacks_multiple_callbacks() -> None:
    results: list[str] = []

    def callback_a(x: int) -> None:
        results.append(f"a:{x}")

    def callback_b(x: int) -> None:
        results.append(f"b:{x}")

    def callback_c(x: int) -> None:
        results.append(f"c:{x}")

    combined = sequence_callbacks(callback_a, callback_b, callback_c)
    combined(5)

    assert results == ["a:5", "b:5", "c:5"]


def test_sequence_callbacks_preserves_order() -> None:
    order: list[int] = []

    def make_callback(n: int) -> Callable:
        def callback() -> None:
            order.append(n)

        return callback

    combined = sequence_callbacks(
        make_callback(1),
        make_callback(2),
        make_callback(3),
    )
    combined()

    assert order == [1, 2, 3]


def test_sequence_callbacks_passes_kwargs() -> None:
    captured: list[dict] = []

    def callback(a: int, b: str, c: bool = False) -> None:
        captured.append({"a": a, "b": b, "c": c})

    combined = sequence_callbacks(callback, callback)
    combined(1, b="hello", c=True)

    assert captured == [
        {"a": 1, "b": "hello", "c": True},
        {"a": 1, "b": "hello", "c": True},
    ]
