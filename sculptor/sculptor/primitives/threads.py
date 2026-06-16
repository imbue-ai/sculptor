"""Thread primitives for sculptor.

ObservableThread - Thread that propagates exceptions and returns results.
"""

import threading
from queue import Queue
from typing import Callable
from typing import Generic
from typing import TypeVar

from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.thread_utils import ObservableThread

T = TypeVar("T")

_POLL_THREAD_SHUTDOWN_TIMEOUT_IN_SECONDS = 10.0


class StopGapBackgroundPollingStreamSource(Generic[T]):
    """
    DONT USE THIS PATTERN.

    This is a stopgap until we implement a proper service-oriented watcher stream in the git repo service
    """

    def __init__(
        self,
        polling_callback: Callable[[], T | None],
        output_queue: Queue[T],
        check_interval_in_seconds: float,
        concurrency_group: ConcurrencyGroup,
    ) -> None:
        self.polling_callback = polling_callback
        self.output_queue = output_queue
        self.check_interval_in_seconds = check_interval_in_seconds
        self.last_seen: T | None = None
        self.stop_event = threading.Event()
        self.thread = ObservableThread(target=self._poll_into_queue)
        self.concurrency_group = concurrency_group

    def _poll_into_queue(self) -> None:
        # Wait at the beginning rather than end so that we don't race with stream tests
        while not self.stop_event.wait(self.check_interval_in_seconds):
            next_value = self.polling_callback()
            if next_value is not None and next_value != self.last_seen:
                self.output_queue.put(next_value)
                self.last_seen = next_value

    def start(self) -> None:
        self.concurrency_group.start_thread(self.thread)

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(_POLL_THREAD_SHUTDOWN_TIMEOUT_IN_SECONDS)
        if self.thread.is_alive():
            logger.error("Polling thread did not shut down in time.")
