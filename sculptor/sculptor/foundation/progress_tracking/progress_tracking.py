"""
Progress tracking utilities.

These are placeholder base classes and common utilities that have minimal dependencies.

For now, we are working on plumbing these into various parts of the system. We will
expand these interfaces and add "real" implementations as we go.
"""

import abc
from contextlib import contextmanager
from typing import Callable
from typing import Generator
from typing import Generic
from typing import Sequence
from typing import TypeVar


class StartFinishHandle(abc.ABC):
    """A handle that supports start/finish reporting."""

    @abc.abstractmethod
    def on_start(self) -> None:
        """Called when the operation is started."""
        ...

    @abc.abstractmethod
    def finish(self) -> None:
        """Report that the operation has finished successfully."""
        ...

    @abc.abstractmethod
    def report_failure(self, explanation: str) -> None:
        """Report that the operation has failed."""
        ...


StartFinishHandleT = TypeVar("StartFinishHandleT", bound=StartFinishHandle, covariant=True)


class UnstartedHandle(Generic[StartFinishHandleT]):
    def __init__(self, handle: StartFinishHandleT) -> None:
        self.handle = handle

    def start(self) -> StartFinishHandleT:
        self.handle.on_start()
        return self.handle


def get_unstarted(handle_factory: Callable[[], StartFinishHandleT]) -> UnstartedHandle[StartFinishHandleT]:
    return UnstartedHandle(handle_factory())


@contextmanager
def start_finish_context(
    unstarted_handle: UnstartedHandle[StartFinishHandleT],
) -> Generator[StartFinishHandleT, None, None]:
    """Context manager to facilitate generic start/finish reporting.

    Example usage:
    with start_finish_context(handle.track_subprocess("Pulling recent changes")) as subprocess_handle:
        # do work with subprocess_handle
    """
    handle = unstarted_handle.start()
    try:
        yield handle
    except Exception as e:
        handle.report_failure(str(e))
        raise
    else:
        handle.finish()


class ProgressHandle(StartFinishHandle):
    """Handle for overall progress of multiple operations."""

    def on_start(self) -> None: ...

    def finish(self) -> None: ...

    def report_failure(self, explanation: str) -> None: ...

    def track_subprocess(self, description: str | None = None) -> UnstartedHandle["SubprocessHandle"]:
        """Get a handle for tracking a subprocess."""
        return get_unstarted(SubprocessHandle)


class SubprocessHandle(StartFinishHandle):
    """Handle for subprocess progress."""

    def on_start(self) -> None: ...

    def finish(self) -> None: ...

    def report_failure(self, explanation: str) -> None: ...

    def report_command(self, command: str | Sequence[str]) -> None:
        """Report the command being run."""
        pass

    def report_output_line(self, line: str, is_stderr: bool) -> None:
        """Report a line of output from the subprocess."""
        pass

    def report_return_code(self, return_code: int) -> None:
        """Report the return code of the subprocess."""
        pass


class TaskTitleProgressHandle(ProgressHandle):
    """Progress handle for task title generation operations."""

    def on_start(self) -> None: ...

    def finish(self) -> None: ...

    def report_failure(self, explanation: str) -> None: ...

    def report_generated_title(self, task_title: str) -> None:
        """Report the generated task title."""
        pass


class RootProgressHandle:
    """Root progress handle that can create scoped progress handles (e.g. on a per-task basis)."""

    def track_task_title_generation(self) -> UnstartedHandle[TaskTitleProgressHandle]:
        """Get a progress handle for tracking task title generation."""
        return get_unstarted(TaskTitleProgressHandle)

    def track_environment_setup(self, task_id: str) -> UnstartedHandle[ProgressHandle]:
        """Get a progress handle for tracking workspace environment setup."""
        return get_unstarted(ProgressHandle)
