import threading
import time
from contextlib import contextmanager
from enum import Enum
from functools import wraps
from typing import Any
from typing import Callable
from typing import Generator
from typing import ParamSpec
from typing import TypeVar

from loguru import logger
from pydantic import PrivateAttr

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.errors import ExpectedError
from sculptor.foundation.pydantic_serialization import MutableModel

# Threshold for TIMING LOG messages - only log if duration exceeds this value
TIMING_LOG_THRESHOLD_SECONDS: float = 0.05  # 50ms

P = ParamSpec("P")
T = TypeVar("T")


def format_timing_log(
    function_name: str,
    duration: float,
    is_operation_successful: bool = True,
    attributes: dict[str, Any] | None = None,
) -> str:
    """
    Format a timing log message in a machine-parseable format.

    Format: TIMING_LOG, function=<name>, duration_s=<00.000000>, status=<success|failed>[, attributes=<dict>]
    """
    status = "success" if is_operation_successful else "failed"
    parts = [
        "TIMING_LOG",
        f"function={function_name}",
        f"duration_s={duration:09.6f}",
        f"status={status}",
    ]
    if attributes:
        parts.append(f"attributes={attributes}")
    return ", ".join(parts)


class TimeoutException(ExpectedError):
    pass


class TimingAttributes(MutableModel):
    """
    Wrapper for timing attributes dictionary used in log_runtime context manager.
    Provides a type-safe way to set timing attributes.
    """

    _attributes: dict[str, bool | float | int | Enum] = PrivateAttr(default_factory=dict)


def monitor_thread(timeout: float, finished_event: threading.Event, on_timeout: Callable[[float], None]) -> None:
    if not finished_event.wait(timeout):
        on_timeout(timeout)


def raise_timeout_exception(timeout: float) -> None:
    raise TimeoutException(f"Timeout of {timeout}s exceeded")


@contextmanager
def timeout_monitor(
    concurrency_group: ConcurrencyGroup, timeout: float, on_timeout: Callable[[float], None] = raise_timeout_exception
) -> Generator[None, None, None]:
    finished_event = threading.Event()
    monitor = concurrency_group.start_new_thread(target=monitor_thread, args=(timeout, finished_event, on_timeout))
    try:
        yield
    finally:
        finished_event.set()
        monitor.join()


@contextmanager
def log_runtime(function_name: str) -> Generator[TimingAttributes, None, None]:
    is_operation_successful = False
    timing_attributes = TimingAttributes()
    start_time = time.monotonic()
    try:
        yield timing_attributes
        is_operation_successful = True
    finally:
        end_time = time.monotonic()
        duration = end_time - start_time
        timing_details = timing_attributes._attributes
        if duration >= TIMING_LOG_THRESHOLD_SECONDS:
            logger.debug(
                format_timing_log(
                    function_name,
                    duration,
                    is_operation_successful,
                    timing_details if timing_details else None,
                )
            )


# when we upgrade to python 3.12 we can make this function generic.
def log_runtime_decorator(label: str | None = None) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator version of log_runtime context manager.

    Usage:
        @log_runtime_decorator("processing data")
        def my_function():
            # function code

        @log_runtime_decorator()  # Uses function name as label
        def another_function():
            # function code
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            func_label = label if label is not None else func.__name__
            with log_runtime(func_label):
                return func(*args, **kwargs)

        return wrapper

    return decorator
