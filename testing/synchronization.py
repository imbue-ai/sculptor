"""Utilities for synchronizing distributed test workers in sculptor."""

import fcntl
import fnmatch
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from imbue_core.git import get_git_repo_root


def get_dist_lockfile_path() -> Path:
    """Get the path to the flock file used for build coordination."""
    return get_git_repo_root() / "sculptor" / ".flock_build_dist"


def cleanup_lockfile(file: Path) -> bool:
    """Clean up the lockfile if it exists and return True if a file was detected."""
    if file.exists():
        file.unlink(missing_ok=True)  # We just want it gone.
        return True
    return False


@contextmanager
def request_lock(lock_filename: str) -> Generator[bool, None, None]:
    """Returns true if you were the first to acquire the lock, false otherwise.

    The lock is held until the context is exited.
    """
    try:
        with open(lock_filename, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield True
    except BlockingIOError:
        yield False


def wait_for_file_existence(path: Path, pattern: str, timeout: float | None = None):
    handler = PatternMatchingHandler(pattern)
    observer = Observer()

    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    if any(fnmatch.fnmatch(str(p), pattern) for p in path.glob("*")):
        # File already exists, no need to wait
        return

    try:
        observer.schedule(handler, path=str(path), recursive=True)
        observer.start()
        if not handler.event.wait(timeout=timeout):
            raise TimeoutError(f"Timed out waiting for file matching pattern: {pattern}")
    finally:
        observer.stop()
        try:
            observer.join()
        except RuntimeError:
            # EAFP Thread was never started
            pass


class PatternMatchingHandler(FileSystemEventHandler):
    """A simple handler that will notify you when the file is ready.

    You can wait on the event.
    """

    def __init__(self, pattern: str) -> None:
        self.event = threading.Event()
        self.pattern = pattern

    def on_created(self, event) -> None:
        if fnmatch.fnmatch(str(event.src_path), self.pattern):
            self.event.set()
