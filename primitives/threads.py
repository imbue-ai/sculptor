"""Thread primitives for sculptor.

ObservableThread - Thread that propagates exceptions and returns results.
"""

import threading
from contextlib import contextmanager
from queue import Queue
from typing import Callable
from typing import Generator
from typing import Generic
from typing import TypeVar

from loguru import logger

from imbue_core.thread_utils import ObservableThread

T = TypeVar("T")


class StopGapBackgroundPollingStreamSource(Generic[T]):
    """
    DONT USE THIS PATTERN.

    This is a stopgap until we implement a proper service-oriented watcher stream in the git repo service
    """

    def __init__(
        self, polling_callback: Callable[[], T | None], output_queue: Queue[T], check_interval_in_seconds: float
    ) -> None:
        self.polling_callback = polling_callback
        self.output_queue = output_queue
        self.check_interval_in_seconds = check_interval_in_seconds
        self.last_seen: T | None = None
        self.stop_event = threading.Event()
        self.thread = ObservableThread(target=self._poll_into_queue)

    def _poll_into_queue(self) -> None:
        # Wait at the beginning rather than end so that we don't race with stream tests
        # NOTE: This is a fragile way of kicking the can down the road and only OK because this code will be deleted soon
        # For more details see https://imbue-ai.slack.com/archives/C0799HVGR7W/p1756224007399819?thread_ts=1756167274.841479&cid=C0799HVGR7W
        while not self.stop_event.wait(self.check_interval_in_seconds):
            next_value = self.polling_callback()
            if next_value is not None and next_value != self.last_seen:
                self.output_queue.put(next_value)
                self.last_seen = next_value

    @contextmanager
    def thread_polling_into_queue(self) -> Generator[None, None, None]:
        """Context manager to start and stop the polling thread."""
        self.thread.start()
        try:
            yield
        finally:
            self.stop_event.set()
            self.thread.join()
        if self.thread.is_alive():
            logger.error("File watcher thread did not shut down in time.")
