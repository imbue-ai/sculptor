"""
Defines 3 main functions for interacting with processes:
- run_blocking: Runs a command and waits for it to complete, returning all output at once.
- run_streaming: Runs a command and waits for it to complete, calling a callback for each line of output as it's produced.
- run_background: Starts a command in the background, returning a RunningProcess object to manage it and access output via a queue.

Avoid using the builtin subprocess module directly; use these functions instead for consistent behavior.

Examples of errors avoided by these wrappers:
- Blocking indefinitely on process output if the output buffer fills up.
- Inconsistent handling of stdout/stderr output.
- Difficulty interrupting long-running processes cleanly.
- Processing streaming output in real-time.
"""

from __future__ import annotations

import contextvars
import logging
import signal
import subprocess
from pathlib import Path
from queue import Queue
from subprocess import TimeoutExpired
from threading import Event
from threading import Thread
from typing import Any
from typing import Callable
from typing import IO
from typing import Mapping
from typing import Sequence
from typing import TypeVar

from loguru import logger

from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.foundation.subprocess_utils import run_local_command_modern_version
from sculptor.foundation.subprocess_utils import send_shutdown_signal
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.foundation.thread_utils import is_exception_irrecoverable

_logger = logging.getLogger(__name__)


def run_blocking(
    command: Sequence[str],
    timeout: float | None = None,
    is_checked: bool = True,
    is_output_traced: bool = False,
    trace_on_line_callback: Callable[[str, bool], None] | None = None,
    cwd: Path | None = None,
    trace_log_context: Mapping[str, object] | None = None,
    shutdown_event: MutableEvent | None = None,
    shutdown_timeout_sec: float = 30.0,
    poll_time: float = 0.01,
    env: Mapping[str, str] | None = None,
) -> FinishedProcess:
    """
    Run a subprocess command in a blocking manner with consistent output handling.

    This function wraps subprocess execution to provide a single, interruptible function call
    similar to subprocess.run, but with added features for consistent output handling and
    interruption support. While the output streaming capability is more relevant for
    run_streaming and run_background, this function provides the foundation for consistent
    process execution across the codebase.

    Args:
        command: The command to execute as a sequence of strings (e.g., ['echo', 'hello'])
        timeout: Maximum time in seconds to wait for the command to complete
        is_checked: If True, raises an exception if the command returns non-zero exit code
        is_output_traced: If True, enables output tracing/logging. Off by default.
        trace_on_line_callback: A callback which will be called once per line that is called
        cwd: Working directory for the command execution. MUST be passed if is_output_traced
        trace_log_context: Additional context to include in trace logs
        shutdown_event: Event that can be used to interrupt the command execution
        shutdown_timeout_sec: Timeout in seconds when shutting down via shutdown_event
        poll_time: Time in seconds to wait between polls to check if the process is finished.
        env: Environment variables to pass to subprocess.Popen

    Returns:
        FinishedProcess: Object containing returncode, stdout, stderr, and command info

    Raises:
        ProcessError: If is_checked=True and the command returns non-zero exit code
        ProcessTimeoutError: If the command exceeds the specified timeout
        ProcessSetupError: If the command was never able to start executing
    """
    return run_local_command_modern_version(
        command=command,
        is_checked=is_checked,
        timeout=timeout,
        trace_output=is_output_traced,
        trace_on_line_callback=trace_on_line_callback if is_output_traced else None,
        cwd=cwd,
        trace_log_context=trace_log_context,
        shutdown_event=shutdown_event,
        shutdown_timeout_sec=shutdown_timeout_sec,
        poll_time=poll_time,
        env=env,
    )


def run_streaming(
    command: Sequence[str],
    on_output: Callable[[str, bool], None],
    is_checked: bool = True,
    timeout: float | None = None,
    cwd: Path | None = None,
    trace_log_context: Mapping[str, object] | None = None,
    shutdown_event: MutableEvent | None = None,
    shutdown_timeout_sec: float = 30.0,
    env: Mapping[str, str] | None = None,
) -> FinishedProcess:
    """
    Run a subprocess command in a blocking manner with streaming output via callbacks.

    This function wraps subprocess execution to provide real-time output streaming. Unlike
    run_blocking which collects all output, this function calls the provided callback for
    each complete line of output as it's produced. A complete line is one that ends with
    a newline character. Partial lines (without trailing newline) are not passed to the
    callback but are still captured in the returned FinishedProcess.

    Args:
        command: The command to execute as a sequence of strings (e.g., ['echo', 'hello'])
        on_output: Callback function called for each complete line of output. Receives (line, is_stdout)
                   where line includes the newline character and is_stdout is True for stdout, False for stderr.
                   Note: Lines without trailing newlines are not passed to this callback
        is_checked: If True, raises an exception if the command returns non-zero exit code
        timeout: Maximum time in seconds to wait for the command to complete (None for no timeout)
        cwd: Working directory for the command execution
        trace_log_context: Additional context to include in trace logs
        shutdown_event: Event that can be used to interrupt the command execution
        shutdown_timeout_sec: Timeout in seconds when shutting down via shutdown_event
        env: Environment variables to pass to subprocess.Popen

    Returns:
        FinishedProcess: Object containing returncode, stdout, stderr, and command info

    Raises:
        ProcessError: If is_checked=True and the command returns non-zero exit code
        ProcessTimeoutError: If the command exceeds the specified timeout
        ProcessSetupError: If the command was never able to start executing
    """
    return run_local_command_modern_version(
        command=command,
        is_checked=is_checked,
        timeout=timeout,
        trace_output=bool(on_output),
        cwd=cwd,
        trace_on_line_callback=on_output,
        trace_log_context=trace_log_context,
        shutdown_event=shutdown_event,
        shutdown_timeout_sec=shutdown_timeout_sec,
        env=env,
    )


class RunningProcess:
    def __init__(
        self,
        command: Sequence[str],
        output_queue: Queue[tuple[str, bool]] | None,
        shutdown_event: MutableEvent,
        is_checked: bool = False,
        open_stdin: bool = False,
        isolate_process_group: bool = False,
    ) -> None:
        self._command = command
        self._output_queue = output_queue
        self._shutdown_event = shutdown_event
        self._is_checked = is_checked
        self._completed_process: FinishedProcess | None = None
        self._thread: ObservableThread | None = None
        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []
        self._open_stdin = open_stdin
        self._isolate_process_group = isolate_process_group
        self._stdin_pipe: IO[bytes] | None = None
        self._stdin_queue: Queue[str | None] | None = None
        self._stdin_writer_thread: Thread | None = None
        # The live ``subprocess.Popen`` handle, captured via ``on_popen_ready``
        # once the worker thread spawns it. Lets ``kill_now`` signal the process
        # (group) directly without coordinating with that worker thread.
        self._popen: subprocess.Popen[bytes] | None = None

    def read_stdout(self) -> str:
        return "".join(self._stdout_lines)

    def read_stderr(self) -> str:
        return "".join(self._stderr_lines)

    def get_queue(self) -> Queue[tuple[str, bool]]:
        assert self._output_queue is not None, "Output queue must be set to get the queue for RunningProcess"
        return self._output_queue

    @property
    def returncode(self) -> int | None:
        return self.poll()

    @property
    def is_checked(self) -> bool:
        return self._is_checked

    @property
    def command(self) -> Sequence[str]:
        """Human-readable command string."""
        return self._command

    def wait_and_read(self, timeout: float | None = None) -> tuple[str, str]:
        self.wait(timeout)
        return self.read_stdout(), self.read_stderr()

    def wait(self, timeout: float | None = None) -> int:
        thread = self._thread
        assert thread is not None, "Thread must be started before waiting"
        if thread.is_alive():
            thread.join(timeout)
        if thread.is_alive():
            stdout = self.read_stdout()
            stderr = self.read_stderr()
            # only reachable when a non-None timeout elapsed: join(None) waits for thread death
            # pyrefly: ignore [bad-argument-type]
            raise TimeoutExpired(self._command, timeout, stdout, stderr)
        result = self.poll()
        if result is None:
            raise ProcessSetupError(
                command=tuple(self._command),
                stdout="",
                stderr="Process exited before being started!",
                is_output_already_logged=True,
            )
        if self._is_checked:
            self.check()
        return result

    def check(self) -> None:
        if self.returncode is not None and self.returncode != 0:
            stdout, stderr = self.read_stdout(), self.read_stderr()
            raise ProcessError(tuple(self._command), stdout, stderr, self.returncode)

    def poll(self) -> int | None:
        thread = self._thread
        if thread is None or thread.native_id is None:
            # Not started yet.
            return None
        if self._completed_process is not None:
            return self._completed_process.returncode

        # if the thread has died, we need to return a fake exit code
        if not thread.is_alive():
            # double check if the process is done:
            if self._completed_process is not None:
                return self._completed_process.returncode
            # and if not, also see if there was an exception
            if thread.exception_raw is not None:
                thread.join()
            # this died without an exception
            return 1007

        return None

    def is_finished(self) -> bool:
        try:
            return self.poll() is not None
        except ProcessSetupError:
            return True

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        self._shutdown_event.set()
        thread = self._thread
        assert thread is not None
        thread.join(timeout=force_kill_seconds)
        if thread.is_alive():
            stdout = self.read_stdout()
            stderr = self.read_stderr()
            raise TimeoutExpired(self._command, force_kill_seconds, stdout, stderr)

    def kill_now(self, sig: signal.Signals) -> None:
        """Send ``sig`` to the process (group) immediately from the caller's thread.

        Unlike ``terminate`` — which sets the shutdown event and lets the worker
        thread's own shutdown path deliver the signal after a join timeout — this
        fires the signal directly, with no shutdown event, no thread join, and no
        ``force_kill_seconds`` budget. That distinction matters when the worker
        thread is itself wedged: a caller (e.g. ``interrupt_current_message``)
        must be able to SIGKILL a hung process's group without depending on that
        thread making any progress.

        When this process was started with ``isolate_process_group=True`` the
        signal is broadcast to the whole process group (``os.killpg``), so
        subprocesses the child spawned die too (SCU-211). No-op if the process
        was never spawned (``on_popen_ready`` never fired).
        """
        popen = self._popen
        if popen is None:
            return
        send_shutdown_signal(popen, sig, kill_process_group=self._isolate_process_group)

    def _set_popen(self, popen: subprocess.Popen[bytes]) -> None:
        """Capture the live Popen handle (fired via ``on_popen_ready`` at spawn)."""
        self._popen = popen

    def start(self, kwargs: dict) -> None:
        # Spawning a thread is an implementation detail of this class.
        # The caller should not have to worry about contextvars (e.g the loguru logging context).
        context = contextvars.copy_context()
        queue: Queue[BaseException | None] = Queue(maxsize=1)
        on_initialized = lambda maybe_exception: queue.put_nowait(maybe_exception)  # noqa: E731
        extra_kwargs: dict[str, Any] = {
            "on_initialization_complete": on_initialized,
            "isolate_process_group": self._isolate_process_group,
            "on_popen_ready": self._set_popen,
        }
        if self._open_stdin:
            extra_kwargs["stdin_mode"] = subprocess.PIPE
            extra_kwargs["on_stdin_ready"] = self._set_stdin_pipe
        self._thread = ObservableThread(
            target=lambda: context.run(self.run, {**kwargs, **extra_kwargs}),
            name=self._get_name(),
            silenced_exceptions=(ProcessError,),
        )
        self._thread.start()
        maybe_initialization_exception = queue.get()
        if maybe_initialization_exception is not None:
            raise maybe_initialization_exception

    def _get_name(self) -> str:
        return f"RunningProcess: {' '.join(self._command)}"

    def run(self, kwargs: dict) -> None:
        # SCU-1265: catch any exception raised inside the inner subprocess
        # wrapper thread. If we let it propagate out of `threading.Thread`,
        # `threading.excepthook` fires (the literal "Exception in thread
        # Thread-N" stderr emit from the ticket's production trace) and any
        # downstream code that tracks this thread sees it as a failed
        # strand — which can wedge the backend.
        #
        # `except BaseException` (not `except Exception`) is intentional: in
        # a thread, KeyboardInterrupt / SystemExit don't terminate the
        # program by default, and we don't want them escaping the thread
        # either. Irrecoverable exceptions (per the
        # ObservableThread-configured handler) are explicitly re-raised
        # below so the program-level crash path still fires.
        #
        # The exception is still surfaced through normal channels:
        #   - For startup failures, `run_local_command_modern_version` fires
        #     `on_initialization_complete(e)` inside its `call_on_exit` block
        #     before unwinding. `RunningProcess.start` reads the exception
        #     off the initialization queue and re-raises it in the main
        #     thread, so the caller still sees it.
        #   - For runtime failures (Popen succeeded then the streaming loop
        #     raised), we record the exception on the ObservableThread via
        #     `record_inner_exception` so `poll()` / `wait()` / `maybe_raise()`
        #     surface it — the same channel that `silenced_exceptions`
        #     already uses for ProcessError.
        try:
            self._completed_process = run_local_command_modern_version(**kwargs)
        except BaseException as e:
            # Don't swallow irrecoverable exceptions — re-raise so
            # ObservableThread.run's outer handler can flush sentry and
            # exit the program. The handler is no-op by default; sculptor
            # registers one via set_irrecoverable_exception_handler.
            if is_exception_irrecoverable(e):
                raise
            # `self._thread` is set by `start()` before `self._thread.start()`,
            # so it is always non-None by the time `run()` executes here.
            # The guard is defensive for type-checkers and any subclass that
            # might invoke `run` outside the normal `start()` path.
            thread = self._thread
            if thread is not None:
                thread.record_inner_exception(e)
            logger.opt(exception=e).error(
                "Unexpected exception in inner subprocess wrapper thread for command {}",
                list(self._command),
            )

    def get_timed_out(self) -> bool:
        if self._completed_process is None:
            return False
        return self._completed_process.is_timed_out

    def on_line(self, line: str, is_stdout: bool) -> None:
        if is_stdout:
            self._stdout_lines.append(line)
        else:
            self._stderr_lines.append(line)
        # pyrefly: ignore [missing-attribute]
        self._output_queue.put((line, is_stdout))

    def _set_stdin_pipe(self, pipe: IO[bytes]) -> None:
        """Callback invoked once the subprocess stdin handle is available.

        Starts a dedicated writer thread that drains ``_stdin_queue`` and
        writes each item to the pipe.  This mirrors the queue-based pattern
        used for stdout/stderr and ensures that callers of ``write_stdin``
        never block on a full pipe buffer.
        """
        self._stdin_pipe = pipe
        self._stdin_queue = Queue()
        self._stdin_writer_thread = Thread(
            target=self._stdin_writer_loop,
            name=f"stdin-writer: {' '.join(self._command)}"[:80],
            daemon=True,
        )
        self._stdin_writer_thread.start()

    def _stdin_writer_loop(self) -> None:
        """Drain ``_stdin_queue``, writing each item to the pipe.

        A ``None`` sentinel signals the loop to close the pipe and exit.
        """
        pipe = self._stdin_pipe
        queue = self._stdin_queue
        assert pipe is not None and queue is not None
        try:
            while True:
                item = queue.get()
                if item is None:
                    break
                pipe.write(item.encode("utf-8"))
                pipe.flush()
        except OSError as exc:
            _logger.debug("stdin writer stopped: %s", exc)
        finally:
            try:
                pipe.close()
            except OSError:
                pass
            self._stdin_pipe = None

    def write_stdin(self, data: str) -> None:
        """Enqueue *data* for writing to the process's stdin.

        The actual write happens on a dedicated thread, so this method never
        blocks on a full pipe buffer.  Only works if started with
        ``open_stdin=True``.
        """
        queue = self._stdin_queue
        assert queue is not None, "Process was not started with open_stdin=True"
        queue.put(data)

    def close_stdin(self) -> None:
        """Signal the stdin writer thread to close the pipe and wait for it to finish."""
        queue = self._stdin_queue
        if queue is not None:
            queue.put(None)  # sentinel
            self._stdin_queue = None
        thread = self._stdin_writer_thread
        if thread is not None:
            thread.join(timeout=5.0)
            self._stdin_writer_thread = None


ProcessClassType = TypeVar("ProcessClassType", bound=RunningProcess)


def run_background(
    command: Sequence[str],
    output_queue: Queue[tuple[str, bool]] | None = None,
    timeout: float | None = None,
    # is_checked is False by default for backwards compatibility
    is_checked: bool = False,
    cwd: Path | None = None,
    trace_log_context: Mapping[str, object] | None = None,
    shutdown_event: MutableEvent | None = None,
    shutdown_timeout_sec: float = 30.0,
    env: Mapping[str, str] | None = None,
    # pyrefly: ignore [bad-function-definition]
    process_class: type[ProcessClassType] = RunningProcess,
    process_class_kwargs: Mapping[str, object] | None = None,
    log_command: bool = True,
    open_stdin: bool = False,
    isolate_process_group: bool = False,
) -> ProcessClassType:
    """
    Run a subprocess command in a non-blocking manner with output handling.

    This function wraps subprocess execution to provide non-blocking process management
    with real-time output streaming via a queue. Unlike run_blocking and run_streaming,
    this function returns immediately with a RunningProcess object that allows the caller
    to either:
    - Access a queue to process output lines as they are produced
    - Wait for completion and read all output at once
    - Check process status, terminate it, or monitor return codes

    Args:
        command: The command to execute as a sequence of strings (e.g., ['echo', 'hello'])
        output_queue: Optional queue for receiving output as (line, is_stdout) tuples.
                      If not provided, a new queue is created. Each line includes newline.
        timeout: Maximum time in seconds for the command to complete (None for no timeout)
        is_checked: If True, creates a RunningProcess whose wait() method raises an error
                    if the command ends up returning a non-zero exit code.
        cwd: Working directory for the command execution
        trace_log_context: Additional context to include in trace logs
        shutdown_event: Event that can be used to interrupt the command execution
        shutdown_timeout_sec: Timeout in seconds when shutting down via shutdown_event

    Returns:
        RunningProcess
    """
    if output_queue is None:
        output_queue = Queue()
    true_shutdown_event = shutdown_event if shutdown_event is not None else Event()
    process = process_class(
        output_queue=output_queue,
        shutdown_event=true_shutdown_event,
        command=command,
        is_checked=is_checked,
        open_stdin=open_stdin,
        isolate_process_group=isolate_process_group,
        **(process_class_kwargs or {}),
    )
    process.start(
        kwargs=dict(
            command=command,
            is_checked=False,
            timeout=timeout,
            trace_output=log_command and bool(process.on_line),
            cwd=cwd,
            trace_on_line_callback=process.on_line,
            trace_log_context=trace_log_context,
            shutdown_event=true_shutdown_event,
            shutdown_timeout_sec=shutdown_timeout_sec,
            env=env,
        )
    )
    return process
