from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from functools import cached_property
from io import BytesIO
from pathlib import Path
from threading import Event
from typing import Callable
from typing import Final
from typing import IO
from typing import Mapping
from typing import Protocol
from typing import Sequence

import attr
from loguru import logger
from typing_extensions import Self

from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.context_managers import call_on_exit
from sculptor.foundation.errors import ExpectedError
from sculptor.foundation.event_utils import CompoundEvent
from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.log_utils import DETAIL
from sculptor.foundation.log_utils import TRACE
from sculptor.foundation.pydantic_serialization import FrozenModel

# Received a shutdown signal
SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE = -9999

# Registry of process groups spawned with ``isolate_process_group=True``.
# Used by ``terminate_isolated_process_groups`` so Sculptor's lifespan
# teardown can forward SIGTERM to agent CLIs that no longer share the
# backend's process group (SCU-211). Without this, the test harness's
# ``killpg(Sculptor pgroup, SIGTERM)`` doesn't reach the agent and the
# SCU-925 invariant ("a clean SIGTERM during AUQ wait must not surface a
# red ErrorBlock on restart") breaks.
_ISOLATED_PROCESS_GROUPS: set[int] = set()
_ISOLATED_PROCESS_GROUPS_LOCK = threading.Lock()


def _register_isolated_process_group(pid: int) -> None:
    with _ISOLATED_PROCESS_GROUPS_LOCK:
        _ISOLATED_PROCESS_GROUPS.add(pid)


def _unregister_isolated_process_group(pid: int) -> None:
    with _ISOLATED_PROCESS_GROUPS_LOCK:
        _ISOLATED_PROCESS_GROUPS.discard(pid)


def terminate_isolated_process_groups(sig: signal.Signals = signal.SIGTERM) -> None:
    """Broadcast *sig* to every process group registered via
    ``isolate_process_group=True``. Best-effort: missing pgroups (already
    exited) are silently ignored.

    Used by Sculptor's lifespan teardown to forward SIGTERM to the agent CLI
    when Sculptor itself is being shut down — without this the agent lives in
    a separate process group (SCU-211) and would be orphaned, leading to the
    SCU-925 red-ErrorBlock regression on restart.
    """
    with _ISOLATED_PROCESS_GROUPS_LOCK:
        pids = tuple(_ISOLATED_PROCESS_GROUPS)
    for pid in pids:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            continue
        if pgid != pid:
            # Same pgid==pid guard as ``send_shutdown_signal``: a stale entry
            # whose process exited and whose PID was reused by an unrelated
            # process in a different group would otherwise be signalled here.
            continue
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            pass


class HasStdoutAndStderr(Protocol):
    stdout: bytes
    stderr: bytes


def log_subprocess_output_line(
    output_line: str,
    relog_loguru_lines: bool = False,
    is_logging_without_loguru_formatting: bool = False,
    # TODO: remove this -- Sculptor code should not be calling this function. Will be fixed in a followup PR.
    is_logging_traced: bool = False,
) -> None:
    log_level = TRACE if is_logging_traced else DETAIL
    output_line = output_line.rstrip("\n")
    # very brittle parsing of log format for recursive logging: ef460144-072f-4b74-a712-0f728fdd3f50
    if len(output_line) >= 36 and output_line[4] == "-" and output_line[7] == "-" and output_line[34:36] == "Tuple ":
        # these lines have already been logged in the child; only relog them if we really want to.
        if relog_loguru_lines:
            logger.opt(raw=True).log(log_level, output_line.rstrip("\n") + "\n")
    else:
        if is_logging_without_loguru_formatting:
            logger.opt(raw=True).log(log_level, output_line.rstrip("\n") + "\n")
        else:
            logger.log(log_level, "> " + output_line)


def maybe_truncate_middle(output: str, size: int) -> str:
    assert size > 1000, "This doesn't handle small sizes nicely"
    if len(output) < size:
        return output
    # Note: not doing any sort of escaping or special formatting because this should only be for human consumption
    truncate_message = f"\n... OUTPUT TRUNCATED DUE TO BEING OVER {size:_} CHARACTERS ...\n"
    truncate_size = (size - len(truncate_message)) // 2 - 1
    return output[:truncate_size] + truncate_message + output[-truncate_size:]


def _stdout_str(has_stdout: "HasStdoutAndStderr") -> str:
    return has_stdout.stdout.decode("utf-8", errors="replace")


def _stderr_str(has_stderr: "HasStdoutAndStderr") -> str:
    return has_stderr.stderr.decode("utf-8", errors="replace")


def _create_output_from_stdout_and_stderr(has_stdout_and_stderr: "HasStdoutAndStderr") -> str:
    return _stdout_str(has_stdout_and_stderr) + _stderr_str(has_stdout_and_stderr)


@attr.s(auto_exc=True, auto_attribs=True)
class CommandError(Exception):
    returncode: int
    stdout: bytes
    stderr: bytes
    command: str
    is_output_already_logged: bool

    stdout_str = property(_stdout_str)
    stderr_str = property(_stderr_str)
    output = cached_property(_create_output_from_stdout_and_stderr)

    def __str__(self) -> str:
        s = f"Command failed with return code {self.returncode}. command=`{self.command}`"
        if not self.is_output_already_logged:
            maybe_truncated_output = maybe_truncate_middle(self.output, 8_000)
            s += f"\noutput:\n{maybe_truncated_output}"
        return s


@attr.s(auto_attribs=True, kw_only=True)
class CompletedProcess:
    """
    Mostly a reimplementation of subprocess.CompletedProcess but allows us to deal with some GI-specific concerns.
    A class to make process results easier to work with for us. We have a couple concerns that are different from typical:
     We run commands over SSH a lot and care about making sure that those errors clearly show both the command being run and the host being run on.
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    command: str
    is_output_already_logged: bool

    stdout_str = property(_stdout_str)
    stderr_str = property(_stderr_str)
    output = cached_property(_create_output_from_stdout_and_stderr)

    def check(self) -> Self:
        if self.returncode != 0:
            error = CommandError(
                command=self.command,
                returncode=self.returncode,
                stdout=self.stdout,
                stderr=self.stderr,
                is_output_already_logged=self.is_output_already_logged,
            )
            if "output" in self.__dict__:
                # We've already calculated the output, so we can just set it here.
                error.output = self.output
            raise error
        # So that this can be chained. For example,
        # hostname = run_local_command("hostname").check().stdout
        return self


class ProcessError(ExpectedError):
    def __init__(
        self,
        command: tuple[str, ...],
        stdout: str,
        stderr: str,
        returncode: int | None = None,
        is_output_already_logged: bool | None = False,
        message: str | None = "Command failed with non-zero exit code",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command
        self.is_output_already_logged = is_output_already_logged
        self.message = message

    def describe(self, is_output_included: bool, output_truncation: int | None = 8_000) -> str:
        command = " ".join(shlex.quote(arg) for arg in self.command)
        s = f"{self.message} {self.returncode}. command=`{command}`"
        if is_output_included:
            output = self.stdout + "\n" + self.stderr
            maybe_truncated_output = maybe_truncate_middle(output, output_truncation) if output_truncation else output
            s += f"\noutput:\n{maybe_truncated_output}"
        return s

    def __str__(self) -> str:
        return self.describe(is_output_included=True)


class ProcessTimeoutError(ProcessError):
    def __init__(
        self,
        command: tuple[str, ...],
        stdout: str,
        stderr: str,
        is_output_already_logged: bool = False,
    ) -> None:
        super().__init__(
            command,
            stdout,
            stderr,
            None,
            is_output_already_logged=is_output_already_logged,
            message="Command timed out",
        )


class ProcessSetupError(ProcessError):
    def __init__(
        self,
        command: tuple[str, ...],
        stdout: str,
        stderr: str,
        is_output_already_logged: bool = False,
    ) -> None:
        super().__init__(
            command,
            stdout,
            stderr,
            None,
            is_output_already_logged=is_output_already_logged,
            message="Command failed to start",
        )


class FinishedProcess(FrozenModel):
    """
    Mostly a reimplementation of subprocess.CompletedProcess but allows us to deal with some GI-specific concerns.
    A class to make process results easier to work with for us. We have a couple concerns that are different from typical:
     We run commands over SSH a lot and care about making sure that those errors clearly show both the command being run and the host being run on.
    """

    returncode: int | None = None
    stdout: str
    stderr: str
    command: tuple[str, ...]
    is_timed_out: bool = False
    is_output_already_logged: bool

    def check(self) -> Self:
        if self.is_timed_out:
            raise ProcessTimeoutError(
                command=self.command,
                stdout=self.stdout,
                stderr=self.stderr,
                is_output_already_logged=self.is_output_already_logged,
            )
        if self.returncode != 0:
            raise ProcessError(
                command=self.command,
                returncode=self.returncode,
                stdout=self.stdout,
                stderr=self.stderr,
                is_output_already_logged=self.is_output_already_logged,
            )
        # So that this can be chained. For example,
        # hostname = run_local_command("hostname").check().stdout
        return self


_READ_SIZE: Final[int] = 2**20


@attr.s(auto_attribs=True)
class PartialOutputContainer:
    """A helper class to make reconstructing log lines returned by pipe.read() easier."""

    buffer: BytesIO = attr.ib(factory=BytesIO)
    # Note: This in-memory line could become huge if no newlines are output
    in_progress_line: bytearray = attr.ib(factory=bytearray)
    on_complete_line: Callable[[str], None] | None = None

    def write(self, output: bytes) -> None:
        """`output` is the output of pipe.read(), ie a string that may contain newlines."""
        self.buffer.write(output)
        on_complete_line = self.on_complete_line
        if on_complete_line is None:
            # If we don't have a callback, we don't need to do anything else.
            return

        lines = output.splitlines(keepends=True)
        for line in lines:
            self.in_progress_line.extend(line)
            if line.endswith((b"\n", b"\r")):
                on_complete_line(self.in_progress_line.decode("utf-8", errors="replace"))
                self.in_progress_line.clear()

    def get_complete_output(self) -> bytes:
        return self.buffer.getvalue()


@attr.s(auto_attribs=True)
class OutputGatherer:
    stdout: IO[bytes]
    stderr: IO[bytes]
    stdout_container: PartialOutputContainer
    stderr_container: PartialOutputContainer
    shutdown_event: ReadOnlyEvent

    @classmethod
    def build_from_popen(
        cls,
        popen: subprocess.Popen[bytes],
        on_complete_line_from_stdout: Callable[[str], None] | None,
        on_complete_line_from_stderr: Callable[[str], None] | None,
        shutdown_event: ReadOnlyEvent,
    ) -> Self:
        stdout = popen.stdout
        stderr = popen.stderr
        assert stdout is not None
        assert stderr is not None
        # this makes reads on process.stdout nonblocking
        os.set_blocking(stdout.fileno(), False)
        os.set_blocking(stderr.fileno(), False)

        return cls(
            stdout=stdout,
            stderr=stderr,
            stdout_container=PartialOutputContainer(on_complete_line=on_complete_line_from_stdout),
            stderr_container=PartialOutputContainer(on_complete_line=on_complete_line_from_stderr),
            shutdown_event=shutdown_event,
        )

    def gather_output(self) -> None:
        is_more_from_stdout = True
        is_more_from_stderr = True
        # We may drop some output if the shutdown event is set, but that's okay.
        while not self.shutdown_event.is_set() and (is_more_from_stdout or is_more_from_stderr):
            # We always attempt to read from both streams to avoid starvation.
            partial_stdout = self.stdout.read(_READ_SIZE)
            if partial_stdout is not None:
                self.stdout_container.write(partial_stdout)
                is_more_from_stdout = len(partial_stdout) == _READ_SIZE
            else:
                is_more_from_stdout = False
            partial_stderr = self.stderr.read(_READ_SIZE)
            if partial_stderr is not None:
                self.stderr_container.write(partial_stderr)
                is_more_from_stderr = len(partial_stderr) == _READ_SIZE
            else:
                is_more_from_stderr = False

    def get_output(self) -> tuple[bytes, bytes]:
        return self.stdout_container.get_complete_output(), self.stderr_container.get_complete_output()

    def get_incomplete_lines(self) -> tuple[str, str]:
        return self.stdout_container.in_progress_line.decode(
            "utf-8", errors="replace"
        ), self.stderr_container.in_progress_line.decode("utf-8", errors="replace")


def send_shutdown_signal(
    process: subprocess.Popen[bytes],
    sig: signal.Signals,
    kill_process_group: bool,
) -> None:
    """Send *sig* to the child process. When ``kill_process_group`` is True and
    the child has actually become its own process-group leader (via
    ``start_new_session=True``), broadcast the signal to the whole group so
    descendants die too.

    The ``pgid == pid`` guard is critical: if ``setsid`` hasn't landed yet
    (extremely brief race after fork) ``os.getpgid`` returns the *parent's*
    group, and ``killpg`` against that would signal the backend process group
    itself. We fall back to a plain single-PID signal in that case.
    """
    if kill_process_group:
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        if pgid == process.pid:
            try:
                os.killpg(pgid, sig)
                return
            except ProcessLookupError:
                return
    if sig == signal.SIGTERM:
        process.terminate()
    else:
        process.kill()


def _shutdown_popen(
    process: subprocess.Popen[bytes],
    command: str,
    shutdown_timeout_sec: float,
    kill_process_group: bool = False,
) -> int | None:
    logger.debug(
        f"run_local_command: aborting command (via sigterm to {process.pid}, kill_process_group={kill_process_group}) due to signal...\n",
        command=truncate_command(command, 500),
    )
    # this sends SIGTERM, which is "the normal way to politely ask a program to terminate"
    send_shutdown_signal(process, signal.SIGTERM, kill_process_group)
    try:
        process.wait(timeout=shutdown_timeout_sec)
        return process.returncode
    except subprocess.TimeoutExpired as e:
        extra = {"command": command, "shutdown_timeout_sec": str(shutdown_timeout_sec)}
        log_exception(
            e,
            "process didn't die within shutdown_timeout_sec of SIGTERM",
            extra=extra,
            priority=ExceptionPriority.LOW_PRIORITY,
        )
        # this sends SIGKILL which immediately kills the process
        send_shutdown_signal(process, signal.SIGKILL, kill_process_group)
        try:
            process.wait(timeout=2)
            return process.returncode
        except subprocess.TimeoutExpired as e:
            log_exception(e, "process didn't die after kill()", extra=extra, priority=ExceptionPriority.LOW_PRIORITY)
            return None


def _log_input_command(command: str) -> None:
    input_lines = command.splitlines()
    truncation_context = 2
    is_worth_truncating = len(input_lines) > 3 * truncation_context
    if is_worth_truncating:
        input_lines = (
            input_lines[:truncation_context]
            + ["         (...content truncated...)"]
            + input_lines[-truncation_context:]
        )
    for line in input_lines:
        logger.trace("< " + line)


def _is_timeout(timeout_time: float | None = None) -> bool:
    if timeout_time is None:
        return False
    else:
        return time.time() > timeout_time


def _close_popen_output_pipes(process: subprocess.Popen[bytes]) -> None:
    """Close a finished process's stdout/stderr pipe file descriptors.

    ``subprocess.Popen(..., stdout=PIPE, stderr=PIPE)`` otherwise releases those
    fds only when the Popen object is garbage-collected. For background
    processes the live Popen is retained on ``RunningProcess`` (captured via
    ``on_popen_ready``) and the finished ``RunningProcess`` itself lingers on its
    ``ConcurrencyGroup`` until a periodic cleanup tick, so the fds would stay
    open until then. Closing here, once the output has been fully gathered,
    frees them immediately.

    Must only be called AFTER the gather loop has finished reading these pipes —
    never while output is still being gathered from them. Closing read pipes
    flushes nothing, so (unlike stdin) this cannot raise.
    """
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()


def run_local_command(
    command: str,
    is_checked: bool = True,
    timeout: float | None = None,
    trace_output: bool = True,
    cwd: Path | None = None,
    trace_on_complete_line_callback: Callable[[str], None] | None = log_subprocess_output_line,
    trace_log_context: Mapping[str, object] | None = None,
    shutdown_event: Event | CompoundEvent | None = None,
    shutdown_timeout_sec: float = 30.0,
) -> CompletedProcess:
    """
    implementation notes:
    - this function is really tricky to implement well! check with the team before making nontrivial changes
    - the reason it's tricky is that we need to both monitor the shutdown event, while also reading the subprocess
    output in realtime to allow realtime log tracing of the output.
    - we previously had an implementation that used a helper thread to read the output, but never seemed to shutdown
    cleanly and left a mess of warnings in the logs, even though it seemed to be implemented properly.
    - the current implementation aims to use just the main thread to avoid this. but then you need to be very careful
    to avoid anything blocking.
    - thus we set the pipe to nonblocking mode so that reads are nonblocking, and we also don't use readline()
    as that could potentially block/deadlock if the process prints long lines with no newlines.
    - don't redirect the process output to a file, as then the command may detect an interactive terminal and use
    line buffering.
    - DO NOT CHANGE STDIN TO ANYTHING BESIDES DEV NULL, that'll cause race conditions.
    - potentially there's a cleaner implementation using asyncio, but better the devil you know.
    """
    trace_log_context = trace_log_context if trace_log_context is not None else {}
    shutdown_event = shutdown_event or Event()

    if shutdown_event.is_set():
        result = CompletedProcess(
            returncode=SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE,
            stdout=b"",
            stderr=b"",
            command=command,
            is_output_already_logged=trace_output,
        )
        if is_checked:
            result.check()
        return result

    if trace_output:
        _log_input_command(command)

    # with bufsize 0 and not setting text, encoding, or errors, the pipe objects will be RawIOBase.
    # use read(2**30) or similar if using this for a nonblocking read.
    # with nonzero bufsize, they will be BufferedIOBase. use read1() if using this for a nonblocking read.
    # with text, encoding, or errors, they will be TextIOBase.
    # this doesn't seem to play nice with nonblocking mode and read().
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=True,
        executable="/bin/bash",
        bufsize=0,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "TERM": "dumb"},
    )

    gatherer = OutputGatherer.build_from_popen(
        process,
        on_complete_line_from_stdout=trace_on_complete_line_callback if trace_output else None,
        on_complete_line_from_stderr=trace_on_complete_line_callback if trace_output else None,
        shutdown_event=shutdown_event,
    )

    timeout_time = time.time() + timeout if timeout is not None else None

    with logger.contextualize(**trace_log_context):
        while not shutdown_event.wait(0.001) and not _is_timeout(timeout_time):
            maybe_exit_code = process.poll()
            gatherer.gather_output()
            if maybe_exit_code is not None:
                exit_code = maybe_exit_code
                break
        else:
            # The shutdown event was set or a timeout limit has been reached,
            # so we should shutdown the process.
            _shutdown_popen(process, command, shutdown_timeout_sec)
            exit_code = SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE

    stdout, stderr = gatherer.get_output()
    # Output is fully gathered (the gather loop has exited); release the pipe fds
    # deterministically instead of waiting for the Popen to be garbage-collected.
    _close_popen_output_pipes(process)
    result = CompletedProcess(
        returncode=exit_code,
        stdout=stdout,
        stderr=stderr,
        command=command,
        is_output_already_logged=trace_output,
    )
    if is_checked:
        result.check()

    return result


# NOTE: this function is largely duplicated with the above, but subtle changes to the types
#  most of the logic should be the same though, with the exception that we assume stdout and stderr are strings
def run_local_command_modern_version(
    command: Sequence[str],
    is_checked: bool = True,
    timeout: float | None = None,
    trace_output: bool = False,
    cwd: Path | None = None,
    # this is called for each line, including the last line even if it doesn't end with a newline
    # if there is no output, it is never called
    trace_on_line_callback: Callable[[str, bool], None] | None = None,
    trace_log_context: Mapping[str, object] | None = None,
    shutdown_event: MutableEvent | None = None,
    shutdown_timeout_sec: float = 30.0,
    poll_time: float = 0.01,
    env: Mapping[str, str] | None = None,
    # This callback gets called once either the process is running or it failed to start.
    # The argument is None on success, or the Exception on failure.
    on_initialization_complete: Callable[[BaseException | None], None] = lambda success: None,
    # Stdin mode for the subprocess. Defaults to subprocess.DEVNULL (no stdin).
    # Set to subprocess.PIPE to enable writing to the process's stdin.
    # When using PIPE, use on_stdin_ready to capture the stdin handle.
    stdin_mode: int = subprocess.DEVNULL,
    # Called with the process's stdin handle immediately after Popen creation.
    # Only useful when stdin_mode=subprocess.PIPE.
    on_stdin_ready: Callable[[IO[bytes]], None] | None = None,
    # Called with the ``subprocess.Popen`` handle immediately after it is
    # created, parallel to ``on_stdin_ready``. This hands the live process out
    # to the caller so it can signal it directly (e.g. ``os.killpg``) without
    # going through the shutdown_event / worker-thread shutdown path — which is
    # exactly what's needed when that worker thread is itself wedged. See
    # ``RunningProcess.kill_now`` (SCU-1340).
    on_popen_ready: Callable[[subprocess.Popen[bytes]], None] | None = None,
    # When True, spawn the child with ``start_new_session=True`` so it becomes
    # its own process-group leader, and broadcast SIGTERM/SIGKILL to that
    # group on shutdown (via ``os.killpg``) instead of just the child PID.
    # This is what makes Stop cascade to subprocesses the child has spawned
    # (e.g. a Bash tool's sh subprocess); see SCU-211.
    isolate_process_group: bool = False,
) -> FinishedProcess:
    """
    implementation notes:
    - this function is really tricky to implement well! check with the team before making nontrivial changes
    - the reason it's tricky is that we need to both monitor the shutdown event, while also reading the subprocess
    output in realtime to allow realtime log tracing of the output.
    - we previously had an implementation that used a helper thread to read the output, but never seemed to shutdown
    cleanly and left a mess of warnings in the logs, even though it seemed to be implemented properly.
    - the current implementation aims to use just the main thread to avoid this. but then you need to be very careful
    to avoid anything blocking.
    - thus we set the pipe to nonblocking mode so that reads are nonblocking, and we also don't use readline()
    as that could potentially block/deadlock if the process prints long lines with no newlines.
    - don't redirect the process output to a file, as then the command may detect an interactive terminal and use
    line buffering.
    - DO NOT CHANGE STDIN TO ANYTHING BESIDES DEV NULL, that'll cause race conditions.
      Exception: callers may opt in to stdin=PIPE via the stdin_mode parameter when they need
      bidirectional communication (e.g. Claude Code's stdin control protocol).
    - potentially there's a cleaner implementation using asyncio, but better the devil you know.
    - if `env` is set, will overwrite contents passed into subprocess.Popen

    raises ProcessError
    """
    with call_on_exit(on_initialization_complete):
        trace_log_context = trace_log_context if trace_log_context is not None else {}
        shutdown_event = shutdown_event or Event()
        command_as_string = " ".join(shlex.quote(arg) for arg in command)
        # NOTE: We create the process even when shutdown_event is already set.
        # It will be terminated almost immediately after starting but the benefit is that the behavior stays consistent.

        if trace_output:
            _log_input_command(command_as_string)

        # with bufsize 0 and not setting text, encoding, or errors, the pipe objects will be RawIOBase.
        # use read(2**30) or similar if using this for a nonblocking read.
        # with nonzero bufsize, they will be BufferedIOBase. use read1() if using this for a nonblocking read.
        # with text, encoding, or errors, they will be TextIOBase.
        # this doesn't seem to play nice with nonblocking mode and read().
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                bufsize=0,
                stdin=stdin_mode,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=isolate_process_group,
            )
        except (OSError, ValueError) as e:
            # Raise setup error if process fails to start.
            #   OSError: subprocess.Popen fails to start the requested command
            #   ValueError: subprocess.Popen malformed arguments
            raise ProcessSetupError(
                command=tuple(command),
                stdout="",
                stderr="",
                is_output_already_logged=trace_output,
            ) from e

        if on_stdin_ready is not None and process.stdin is not None:
            on_stdin_ready(process.stdin)

        if on_popen_ready is not None:
            on_popen_ready(process)

        if isolate_process_group:
            _register_isolated_process_group(process.pid)

    if trace_on_line_callback is not None:
        on_complete_line_from_stdout = lambda line: trace_on_line_callback(line, True)  # noqa: E731
        on_complete_line_from_stderr = lambda line: trace_on_line_callback(line, False)  # noqa: E731
    else:
        on_complete_line_from_stdout = None
        on_complete_line_from_stderr = None

    gatherer = OutputGatherer.build_from_popen(
        process,
        on_complete_line_from_stdout=on_complete_line_from_stdout,
        on_complete_line_from_stderr=on_complete_line_from_stderr,
        shutdown_event=shutdown_event,
    )

    timeout_time = time.time() + timeout if timeout is not None else None

    with logger.contextualize(**trace_log_context):
        while not shutdown_event.wait(poll_time) and not _is_timeout(timeout_time):
            maybe_exit_code = process.poll()
            gatherer.gather_output()
            if maybe_exit_code is not None:
                exit_code = maybe_exit_code
                break
        else:
            # The shutdown event was set or a timeout limit has been reached,
            # so we should shutdown the process.
            #
            # Order matters for isolated process groups: send SIGTERM *before*
            # closing stdin. The agent CLI (the only opt-in caller of
            # ``isolate_process_group``) installs a SIGTERM handler that exits
            # with 143 — message_conversion treats that as a clean Stop and
            # suppresses the ErrorBlock (SCU-925). Closing stdin first races
            # with the signal: a CLI blocked reading stdin (e.g. fake_claude
            # waiting on an MCP control_response) sees EOF, raises
            # RuntimeError, and exits with 1 before the SIGTERM handler runs.
            # The wrapper then emits a ``RequestFailureAgentMessage`` and the
            # red "Agent died with exit code 1" block appears on the next
            # restart — the exact regression SCU-925 fixed.
            #
            # For the default (single-PID) path we keep the original order:
            # close stdin first to wake any process blocked on input that
            # doesn't handle SIGTERM, then escalate.
            if not isolate_process_group and process.stdin is not None:
                process.stdin.close()
            exit_code = _shutdown_popen(
                process, command_as_string, shutdown_timeout_sec, kill_process_group=isolate_process_group
            )
            if isolate_process_group and process.stdin is not None:
                process.stdin.close()

    if isolate_process_group:
        _unregister_isolated_process_group(process.pid)

    stdout, stderr = gatherer.get_output()

    # send the final incomplete lines as well
    incomplete_stdout_line, incomplete_stderr_line = gatherer.get_incomplete_lines()
    if incomplete_stdout_line:
        if trace_on_line_callback:
            trace_on_line_callback(incomplete_stdout_line, True)
    if incomplete_stderr_line:
        if trace_on_line_callback:
            trace_on_line_callback(incomplete_stderr_line, False)

    # Output is fully gathered (the gather loop has exited and the incomplete
    # lines come from in-memory containers, not the pipes); release the pipe fds
    # deterministically. The live Popen is retained on RunningProcess, which the
    # ConcurrencyGroup keeps until a cleanup tick, so without this the fds would
    # linger well past process exit.
    _close_popen_output_pipes(process)

    result = FinishedProcess(
        returncode=exit_code,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        command=tuple(command),
        is_timed_out=_is_timeout(timeout_time),
        is_output_already_logged=trace_output,
    )
    if is_checked:
        result.check()

    return result


def truncate_command(command: str, num_chars: int = 2000) -> str:
    """Truncates a command to include just the first `num_chars` of the first line."""
    truncated = False
    split_command = command.split("\n")
    if len(split_command) > 1:
        truncated = True
        command = split_command[0]
    if len(command) > num_chars:
        truncated = True
        command = command[:num_chars]
    if truncated:
        command += "... (truncated)"
    return command
