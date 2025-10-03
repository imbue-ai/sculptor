import threading
from contextlib import contextmanager
from typing import Generator


class ReadWriteLock:
    """A reader-writer lock that allows multiple readers or a single writer.

    Readers share the lock unless a writer is active or waiting. Writers gain
    exclusive access and block new readers until they release the lock.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active_readers = 0
        self._active_writer = False
        self._waiting_writers = 0

    @contextmanager
    def read_lock(self) -> Generator[None, None, None]:
        """Acquire the lock for a reader."""
        with self._condition:
            while self._waiting_writers > 0 or self._active_writer:
                self._condition.wait()
            self._active_readers += 1
        try:
            yield
        finally:
            with self._condition:
                self._active_readers -= 1
                if self._active_readers == 0:
                    self._condition.notify_all()

    @contextmanager
    def write_lock(self) -> Generator[None, None, None]:
        """Acquire the lock for a writer."""
        with self._condition:
            self._waiting_writers += 1
            while self._active_writer or self._active_readers > 0:
                self._condition.wait()
            self._active_writer = True
            self._waiting_writers -= 1
        try:
            yield
        finally:
            with self._condition:
                self._active_writer = False
                self._condition.notify_all()
