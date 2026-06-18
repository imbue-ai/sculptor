from typing import Callable
from typing import ParamSpec

P = ParamSpec("P")


def sequence_callbacks(*callbacks: Callable[P, None]) -> Callable[P, None]:
    """Combine callbacks into one that invokes each in order with the same arguments."""

    def combined_callback(*args: P.args, **kwargs: P.kwargs) -> None:
        for callback in callbacks:
            callback(*args, **kwargs)

    return combined_callback
