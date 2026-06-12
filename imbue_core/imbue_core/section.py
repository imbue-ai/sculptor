"""
Provides a context manager for logging a potentially time-consuming process, or a "section".

- Prints logs at start and end of a section.

- Prints a Markdown-like heading for nested sections: "#" for top-level sections, "##" for one level down, and so on.

- Emits structured logs for easier query.

"""

import contextlib
import threading
import time
from asyncio import CancelledError
from types import TracebackType

from loguru import logger

_monotonic_base = time.monotonic()


def _monotonic_time() -> float:
    """A wrapper around time.monotonic() to make the return values a bit smaller and easier to read by a human."""
    return time.monotonic() - _monotonic_base


class _ThreadLocal(threading.local):
    def __init__(self) -> None:
        self.next_section_level: int = 0


_thread_local = _ThreadLocal()


class Section(contextlib.ContextDecorator):
    def __init__(self, message: str, log_level: int | str = "INFO") -> None:
        self.message = message
        self.log_level = log_level

    def __enter__(self) -> "Section":
        level = _thread_local.next_section_level
        _thread_local.next_section_level += 1
        self.header = "#" * (level + 1)  # pyre-ignore[16]
        self.start_monotonic_time = _monotonic_time()  # pyre-ignore[16]
        start_clock_time = time.time()
        self.section = {  # pyre-ignore[16]
            "name": self.message,
            "level": level,
            "start_monotonic_time": self.start_monotonic_time,
            "start_clock_time": start_clock_time,
        }
        logger.log(
            self.log_level,
            f"{self.header} Start: {self.message}",
            section=self.section,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        _thread_local.next_section_level -= 1
        finish_monotonic_time = _monotonic_time()
        finish_clock_time = time.time()
        # pyre-ignore[16]: we set this on __enter__
        duration_seconds = finish_monotonic_time - self.start_monotonic_time
        section = self.section | {  # pyre-ignore[16]: we set this on __enter__
            "finish_monotonic_time": finish_monotonic_time,
            "finish_clock_time": finish_clock_time,
            "duration_seconds": duration_seconds,
        }
        self.elapsed = duration_seconds  # pyre-ignore[16]

        header = self.header  # pyre-ignore[16]: we set this on __enter__

        if exc_val is None:
            logger.log(
                self.log_level,
                f"{header} Done: {self.message} (took {duration_seconds:.2f} seconds)",
                section=section | {"result": "success"},
            )
        else:
            if isinstance(exc_val, CancelledError):
                logger.log(
                    self.log_level,
                    f"{header} Cancelled: {self.message} (took {duration_seconds:.2f} seconds)",
                    section=section | {"result": "cancelled"},
                )
            else:
                logger.log(
                    self.log_level,
                    f"{header} Failed: {self.message} (within {duration_seconds:.2f} seconds)",
                    section=section | {"result": "failed"},
                )
