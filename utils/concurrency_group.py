"""
This module implements the concept of a Concurrency Group.

Motivation: With how heavily we use threads and processes (collectively called "strands") in Sculptor, it's easy to accidentally leak them
and hard to shut them down gracefully in an organized manner. That can lead to all sorts of hard to debug problems and race conditions.
We would like to have an easy to use mechanism to manage threads and processes in a structured way.

The idea for ConcurrencyGroups is that:
    - Similarly to the DataTransaction concept, we will propagate ConcurrencyGroups through the code from the top level downwards.
    - ConcurrencyGroups can be nested, effectively forming a tree structure with one root for the whole application.
    - You should create threads and processes through the current ConcurrencyGroup.
    - A ConcurrencyGroup, being a context manager, will do basic accounting of its threads and processes upon exiting.
    - Errors will be raised if we forget to join threads or processes or handle their failures.
    - When shutting down the whole application, we will propagate the shutdown event to all threads and processes through the concurrency group tree.

(This is currently still WIP.)

"""

import time
from collections import defaultdict
from contextlib import AbstractContextManager
from enum import StrEnum
from functools import wraps
from subprocess import TimeoutExpired
from threading import Event
from threading import Lock
from typing import Any
from typing import Callable
from typing import Mapping
from typing import Sequence

from pydantic import PrivateAttr

from imbue_core.processes.local_process import RunningProcess
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.subprocess_utils import CompoundEvent
from imbue_core.subprocess_utils import ProcessError
from imbue_core.thread_utils import ObservableThread
from sculptor.interfaces.environments.v1.base import Environment

DEFAULT_EXIT_TIMEOUT_SECONDS = 4.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 4.0


def _raise_if_any_strands_or_ancestors_failed(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        self.raise_if_any_strands_or_ancestors_failed()
        return func(self, *args, **kwargs)

    return wrapper


class ConcurrencyGroupState(StrEnum):
    """
    For sanity, let's postulate that a given concurrency group can only be used once.

    Every concurrency group is in one of the following states:

    """

    INSTANTIATED = "instantiated"
    ACTIVE = "active"
    EXITING = "exiting"
    EXITED = "exited"


class ConcurrencyGroup(MutableModel, AbstractContextManager):
    """
    A context manager to manage threads and processes.

    - Keep track of threads and processes created within the context manager.
    - Ensure that they are cleaned up properly and their failures are handled.
    - Keep track of nested concurrency groups.
    - (TODO) Propagate shutdown events to all threads and processes.

    """

    # When using a concurrency group in conjunction with an environment,
    # we can use it to keep track of environment processes.
    environment: Environment | None = None
    # How long to wait for strands to finish when exiting the context manager.
    exit_timeout_seconds: float = DEFAULT_EXIT_TIMEOUT_SECONDS
    # How long to wait for strands to finish when shutting down the whole application.
    shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
    parent: "ConcurrencyGroup | None" = None
    _state: ConcurrencyGroupState = PrivateAttr(default=ConcurrencyGroupState.INSTANTIATED)
    _threads: list[ObservableThread] = PrivateAttr(default_factory=list)
    _processes: list[RunningProcess] = PrivateAttr(default_factory=list)
    _lock: Lock = PrivateAttr(default_factory=Lock)
    _children: list["ConcurrencyGroup"] = PrivateAttr(default_factory=list)
    _exit_exception: Exception | None = PrivateAttr(default=None)

    def __enter__(self):
        with self._lock:
            if self._state != ConcurrencyGroupState.INSTANTIATED:
                raise InvalidConcurrencyGroupStateError("This concurrency group has been already activated.")
            self._state = ConcurrencyGroupState.ACTIVE
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            with self._lock:
                self._state = ConcurrencyGroupState.EXITING
            self._exit(exc_value)
        except Exception as exit_exception:
            self._exit_exception = exit_exception
            raise
        finally:
            self._state = ConcurrencyGroupState.EXITED

    def _exit(self, exc_value):
        # Assemble the exceptions from all the failure modes that can occur:
        #   - an exception being raised from the main code in the context manager
        #   - any of the threads or processes failing
        #   - timeouts while waiting for threads or processes to finish
        #
        # All of them should be reported if they occur. We use the ExceptionGroup mechanism for that.
        main_exception: Exception | None = exc_value if exc_value is not None else None
        timeout_exception_group: ConcurrencyExceptionGroup | None = None
        failure_exception_group: ConcurrencyExceptionGroup | None = None

        try:
            if self._is_whole_app_shutting_down():
                self._wait_for_all_strands_to_finish_with_timeout(self.shutdown_timeout_seconds)
            else:
                self._wait_for_all_strands_to_finish_with_timeout(self.exit_timeout_seconds)
        except ConcurrencyExceptionGroup as exception_group:
            timeout_exception_group = exception_group

        try:
            self.raise_if_any_strands_or_ancestors_failed()
        except ConcurrencyExceptionGroup as exception_group:
            failure_exception_group = exception_group

        exceptions = []
        message: str | None = None
        if timeout_exception_group is not None:
            exceptions.extend(timeout_exception_group.exceptions)
            message = timeout_exception_group.message
        if failure_exception_group is not None:
            exceptions.extend(failure_exception_group.exceptions)
            message = failure_exception_group.message
        if main_exception is not None:
            if isinstance(main_exception, ConcurrencyExceptionGroup):
                exceptions.extend(main_exception.exceptions)
                message = main_exception.message
            else:
                exceptions.append(main_exception)
                message = str(main_exception)

        # All children concurrency groups should have exited (or not been activated at all) by now.
        # This should be a given but let's double-check that.
        # (It's possible that a child concurrency group is still active if the thread where it was created hangs and hasn't been collected above.)
        for child in self._children:
            if child.state != ConcurrencyGroupState.EXITED:
                exceptions.append(ChildConcurrencyGroupDidNotExitError("A child concurrency group did not exit."))
                message = message or "A child concurrency group did not exit."

        # For consistency, we always raise a ConcurrencyExceptionGroup even if there is only one exception.
        if len(exceptions) > 0:
            exceptions = _deduplicate_exceptions(tuple(exceptions))
            assert message is not None
            if main_exception is not None:
                raise ConcurrencyExceptionGroup(message, exceptions, main_exception=main_exception) from main_exception
            raise ConcurrencyExceptionGroup(message, exceptions)

    def _wait_for_all_strands_to_finish_with_timeout(self, timeout_seconds: float) -> None:
        start_time = time.monotonic()
        timeout_errors: list[StrandTimedOutError] = []
        for process in self._processes:
            if not process.is_finished():
                remaining_timeout = self._get_remaining_timeout(start_time, timeout_seconds)
                try:
                    process.wait(timeout=remaining_timeout)
                except TimeoutExpired as error:
                    command = error.cmd
                    stdout = process.read_stdout()[:1024]  # Avoid huge outputs.
                    stderr = process.read_stderr()[:1024]
                    message = "\n".join(
                        [
                            f"Process {command} did not terminate in time and was killed.",
                            f"Stdout: {stdout}",
                            f"Stderr: {stderr}",
                        ]
                    )
                    timeout_errors.append(StrandTimedOutError(message))
                    # Forcefully terminate the process - this sends sigkill.
                    try:
                        process.terminate(force_kill_seconds=0.0)
                    except TimeoutExpired as errors:
                        pass
        for thread in self._threads:
            remaining_timeout = self._get_remaining_timeout(start_time, timeout_seconds)
            try:
                thread.join(timeout=remaining_timeout)
            except Exception:
                # We suppress exception raised during join() here because we check for failed strands separately.
                pass
            if thread.is_alive():
                timeout_errors.append(
                    StrandTimedOutError(f"Thread {thread.name} did not finish in time and is still alive.")
                )
        if len(timeout_errors) > 0:
            raise ConcurrencyExceptionGroup(
                f"{len(timeout_errors)} strands did not finish in time and were terminated.",
                timeout_errors,
            )

    def _get_remaining_timeout(self, start_time_seconds: float, total_timeout_seconds: float) -> float:
        elapsed_seconds = time.monotonic() - start_time_seconds
        return max(0, total_timeout_seconds - elapsed_seconds)

    def _raise_if_not_active(self):
        if self._state != ConcurrencyGroupState.ACTIVE:
            raise InvalidConcurrencyGroupStateError(f"Concurrency group not active: the state is {self._state}.")

    def raise_if_any_strands_or_ancestors_failed(self):
        """
        Go through all the registered strands and raise an exception if any of them failed.
        Also check if the parent concurrency group failed. (This is used to propagate failures sideways and downwards in the concurrency group tree.)

        This method is public because you might want to call it from within the context manager to see if there were any failures so far.

        """
        exceptions = []
        with self._lock:
            threads = self._threads[:]
            processes = self._processes[:]
        for thread in threads:
            try:
                thread.maybe_raise()
            except Exception as e:
                exceptions.append(e)
        for process in processes:
            if not process.is_checked:
                continue
            if process.returncode is not None and process.returncode != 0:
                exceptions.append(
                    ProcessError(
                        command=tuple(process.command),
                        stdout=process.read_stdout(),
                        stderr=process.read_stderr(),
                        returncode=process.returncode,
                    )
                )
        ancestor_exception = self.maybe_get_closest_ancestor_exception()
        if ancestor_exception is not None:
            exceptions.append(AncestorConcurrentFailure(ancestor_exception))

        if len(exceptions) > 0:
            raise ConcurrencyExceptionGroup(
                f"{len(exceptions)} strands failed in concurrency group.",
                exceptions,
            )

    def _is_whole_app_shutting_down(self) -> bool:
        # TODO: actually implement this. https://linear.app/imbue/issue/PROD-2333
        return False

    @_raise_if_any_strands_or_ancestors_failed
    def start_thread(
        self,
        target: Callable[..., Any],
        args: tuple = (),
        kwargs: dict | None = None,
        name: str | None = None,
        daemon: bool = True,
        silenced_exceptions: tuple[type[BaseException], ...] | None = None,
        suppressed_exceptions: tuple[type[BaseException], ...] | None = None,
    ) -> ObservableThread:
        thread = ObservableThread(
            target=target,
            args=args,
            kwargs=kwargs,
            name=name,
            daemon=daemon,
            silenced_exceptions=silenced_exceptions,
            suppressed_exceptions=suppressed_exceptions,
        )
        with self._lock:
            self._raise_if_not_active()
            thread.start()
            self._threads.append(thread)
        return thread

    @_raise_if_any_strands_or_ancestors_failed
    def run_environment_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        shutdown_event: Event | CompoundEvent | None = None,
        timeout: float | None = None,
        is_checked: bool = True,
    ) -> RunningProcess:
        if self.environment is None:
            raise NoEnvironmentError("No environment is set for this concurrency group.")
        with self._lock:
            self._raise_if_not_active()
            process = self.environment.run_process_in_background(
                command=command,
                secrets=secrets,
                cwd=cwd,
                is_interactive=is_interactive,
                run_with_sudo_privileges=run_with_sudo_privileges,
                run_as_root=run_as_root,
                timeout=timeout,
                shutdown_event=shutdown_event,
                is_checked=is_checked,
            )
            self._processes.append(process)
        return process

    def run_environment_process_to_completion(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        timeout: float | None = None,
        is_checked: bool = True,
    ) -> RunningProcess:
        process = self.run_environment_process_in_background(
            command=command,
            secrets=secrets,
            cwd=cwd,
            is_interactive=is_interactive,
            run_with_sudo_privileges=run_with_sudo_privileges,
            run_as_root=run_as_root,
            timeout=timeout,
            is_checked=is_checked,
        )
        process.wait()
        return process

    @_raise_if_any_strands_or_ancestors_failed
    def make_concurrency_group(
        self,
        environment: Environment | None = None,
        exit_timeout_seconds: float = DEFAULT_EXIT_TIMEOUT_SECONDS,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> "ConcurrencyGroup":
        """
        Create a child concurrency group.

        The child concurrency group will be tracked by the parent and its state will be checked when the parent exits.

        Also, the child concurrency group can see if any of its ancestors failed.

        """
        concurrency_group = ConcurrencyGroup(
            environment=environment,
            parent=self,
            exit_timeout_seconds=exit_timeout_seconds,
            shutdown_timeout_seconds=shutdown_timeout_seconds,
        )
        with self._lock:
            self._raise_if_not_active()
            self._children.append(concurrency_group)
        return concurrency_group

    @property
    def state(self) -> ConcurrencyGroupState:
        return self._state

    @property
    def exit_exception(self) -> Exception | None:
        return self._exit_exception

    def maybe_get_closest_ancestor_exception(self) -> Exception | None:
        """
        Check if any ancestor concurrency group failed and return its exception.

        """
        current = self.parent
        while current is not None:
            if current.state == ConcurrencyGroupState.EXITED and current.exit_exception is not None:
                return current.exit_exception
            current = current.parent
        return None


def _deduplicate_exceptions(exceptions: tuple[Exception, ...]) -> tuple[Exception, ...]:
    """
    Deduplicate accumulated exceptions.

    (They are often duplicated because the main exception is actually a ConcurrencyExceptionGroup
    raised after calling _raise_if_any_strands_or_parent_failed from the main code.)

    """
    # First deduplicate by identity - that weeds out some duplicates.
    exceptions = tuple(set(exceptions))
    # Then special-case failed processes - the same error can be reported when calling wait() in the main code and when probing the process later.
    # (Prefer exceptions with __traceback__.)
    process_error_buckets: dict[tuple, list[ProcessError]] = defaultdict(list)
    other_exceptions = []
    for exception in exceptions:
        if isinstance(exception, ProcessError):
            key = (exception.command, exception.returncode, exception.stdout, exception.stderr)
            process_error_buckets[key].append(exception)
        else:
            other_exceptions.append(exception)
    deduplicated_process_errors = []
    for bucket in process_error_buckets.values():
        with_traceback = [e for e in bucket if e.__traceback__ is not None]
        if len(with_traceback) > 0:
            deduplicated_process_errors.append(with_traceback[0])
        else:
            deduplicated_process_errors.append(bucket[0])
    return tuple(other_exceptions + deduplicated_process_errors)


class NoEnvironmentError(Exception):
    pass


class StrandTimedOutError(Exception):
    pass


class InvalidConcurrencyGroupStateError(Exception):
    pass


class ChildConcurrencyGroupDidNotExitError(Exception):
    pass


class AncestorConcurrentFailure(Exception):
    def __init__(self, ancestor_exception: Exception | None):
        self.ancestor_exception = ancestor_exception
        message = "An ancestor concurrency group failed."
        if ancestor_exception is not None:
            message += f" Ancestor exception: {ancestor_exception}"
        super().__init__(message)


class ConcurrencyExceptionGroup(ExceptionGroup):
    """
    Our own exception group subclass.

    It serves two purposes:
        - We can easily see that the exception group was raised by our code.
        - The "main" exception is a convention that allows us to highlight the "original" exception in cases we know it.
    """

    def __new__(cls, message: str, exceptions: Sequence[Exception], main_exception: Exception | None = None):
        instance = super().__new__(cls, message, exceptions)
        return instance

    def __init__(self, message: str, exceptions: Sequence[Exception], main_exception: Exception | None = None):
        super().__init__(message, exceptions)
        self.main_exception = main_exception

    def __str__(self):
        base_str = super().__str__()
        if self.main_exception:
            return f"{base_str}\nMain exception: {self.main_exception}"
        return base_str
