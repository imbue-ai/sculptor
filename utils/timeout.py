import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable
from typing import Generator
from typing import ParamSpec
from typing import TypeVar

from loguru import logger

from imbue_core.errors import ExpectedError
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry import with_consent
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.thread_utils import ObservableThread

P = ParamSpec("P")
T = TypeVar("T")


class TimeoutException(ExpectedError):
    pass


class RuntimeMeasurementPayload(PosthogEventPayload):
    function_name: str = with_consent(
        ConsentLevel.PRODUCT_ANALYTICS, description="Name of the function being measured"
    )
    duration_seconds: float = with_consent(ConsentLevel.PRODUCT_ANALYTICS, description="Runtime duration in seconds")


def monitor_thread(timeout: float, finished_event: threading.Event, on_timeout: Callable[[float], None]) -> None:
    if not finished_event.wait(timeout):
        on_timeout(timeout)


def raise_timeout_exception(timeout: float) -> None:
    raise TimeoutException(f"Timeout of {timeout}s exceeded")


@contextmanager
def timeout_monitor(
    timeout: float, on_timeout: Callable[[float], None] = raise_timeout_exception
) -> Generator[None, None, None]:
    finished_event = threading.Event()
    monitor = ObservableThread(target=monitor_thread, args=(timeout, finished_event, on_timeout))
    monitor.start()
    try:
        yield
    finally:
        finished_event.set()
        monitor.join()


@contextmanager
def log_runtime(function_name: str) -> Generator[None, None, None]:
    try:
        start_time = time.monotonic()
        yield
    finally:
        end_time = time.monotonic()
        duration = end_time - start_time
        logger.debug("TIMING LOG: {} took {}s to run", function_name, duration)

        # Emit PostHog event for runtime tracking
        try:
            payload = RuntimeMeasurementPayload(function_name=function_name, duration_seconds=duration)
            emit_posthog_event(
                PosthogEventModel(
                    name=SculptorPosthogEvent.RUNTIME_MEASUREMENT,
                    component=ProductComponent.CROSS_COMPONENT,
                    payload=payload,
                )
            )
        except Exception as e:
            # Don't let PostHog errors break the original function
            logger.debug("Failed to emit PostHog runtime event: {}", e)


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
            start_time = time.monotonic()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                logger.debug("TIMING LOG: {} took {}s to run", func_label, duration)

                # Emit PostHog event for runtime tracking
                try:
                    payload = RuntimeMeasurementPayload(function_name=func_label, duration_seconds=duration)
                    emit_posthog_event(
                        PosthogEventModel(
                            name=SculptorPosthogEvent.RUNTIME_MEASUREMENT,
                            component=ProductComponent.CROSS_COMPONENT,
                            payload=payload,
                        )
                    )
                except Exception as e:
                    # Don't let PostHog errors break the original function
                    logger.debug("Failed to emit PostHog runtime event: {}", e)

        return wrapper

    return decorator
