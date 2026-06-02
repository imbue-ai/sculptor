import tempfile
import threading
import time
from pathlib import Path
from queue import Empty
from queue import Queue
from subprocess import TimeoutExpired
from threading import Event
from typing import NoReturn

import pytest

from sculptor.foundation.event_utils import CompoundEvent
from sculptor.foundation.processes import local_process as local_process_module
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.processes.local_process import run_background
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.subprocess_utils import ProcessSetupError

INNER_THREAD_JOIN_TIMEOUT_SEC = 2.0
INNER_THREAD_NAME_PREFIX = "RunningProcess:"


def _join_inner_subprocess_threads() -> None:
    """Deterministically wait for any inner subprocess-wrapper threads to finish.

    Used by the SCU-1265 tests in place of a fixed ``time.sleep``. Looks up
    threads by the name set in ``RunningProcess._get_name`` and joins them with
    a short timeout. Calls ``threading.Thread.join`` directly (the unbound
    base-class method) to bypass ``ObservableThread.join``'s ``maybe_raise``
    — we only want to wait, not re-surface any stored exception.
    """
    for t in list(threading.enumerate()):
        if t.name.startswith(INNER_THREAD_NAME_PREFIX):
            threading.Thread.join(t, timeout=INNER_THREAD_JOIN_TIMEOUT_SEC)


def test_run_background_simple_command() -> None:
    """Test running a simple echo command in background."""
    proc = run_background(["echo", "hello world"])

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 0
    assert stdout.strip() == "hello world"
    assert stderr == ""


def test_run_background_with_queue() -> None:
    """Test that output is properly sent to the queue."""
    output_queue = Queue()
    proc = run_background(["echo", "test output"], output_queue=output_queue)

    proc.wait(timeout=5.0)

    # Read from queue
    line, is_stdout = output_queue.get(timeout=1.0)
    assert line == "test output\n"
    assert is_stdout

    # Queue should be empty now
    with pytest.raises(Empty):
        output_queue.get(block=False)

    assert proc.returncode == 0


def test_run_background_multiline_output() -> None:
    """Test background process with multiple lines of output."""
    proc = run_background(["sh", "-c", "echo 'line1'; echo 'line2'; echo 'line3'"])

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 0
    lines = stdout.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "line1"
    assert lines[1] == "line2"
    assert lines[2] == "line3"


def test_run_background_mixed_stdout_stderr() -> None:
    """Test background process that writes to both stdout and stderr."""
    proc = run_background(["sh", "-c", "echo 'stdout line'; echo 'stderr line' >&2"])

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 0
    assert stdout.strip() == "stdout line"
    assert stderr.strip() == "stderr line"


def test_run_background_real_time_queue() -> None:
    """Test that output is available in real-time via queue."""
    output_queue = Queue()
    start_time = time.time()

    # Command that outputs with delays
    proc = run_background(["sh", "-c", "echo 'immediate'; sleep 0.5; echo 'delayed'"], output_queue=output_queue)

    # Get first line immediately
    line1, is_stdout1 = output_queue.get(timeout=0.2)
    time1 = time.time() - start_time

    # Get second line after delay
    line2, is_stdout2 = output_queue.get(timeout=1.0)
    time2 = time.time() - start_time

    proc.wait(timeout=2.0)

    assert line1 == "immediate\n"
    assert is_stdout1
    assert time1 < 0.3  # First line should come quickly

    assert line2 == "delayed\n"
    assert is_stdout2
    assert time2 > 0.4  # Second line should come after delay

    assert proc.returncode == 0


def test_run_background_poll_and_is_finished() -> None:
    """Test polling and checking if process is finished."""
    # Fast command
    proc = run_background(["echo", "quick"])

    # Initially might still be running
    time.sleep(0.01)

    # Wait for completion
    proc.wait(timeout=5.0)

    # After wait, should be finished
    assert proc.is_finished()
    assert proc.poll() == 0
    assert proc.returncode == 0


def test_run_background_long_running_poll() -> None:
    """Test polling a long-running process."""
    proc = run_background(["sleep", "2"])

    # Should not be finished immediately
    assert not proc.is_finished()
    assert proc.poll() is None
    assert proc.returncode is None

    # Wait for completion
    proc.wait(timeout=5.0)

    # Should be finished now
    assert proc.is_finished()
    assert proc.poll() == 0
    assert proc.returncode == 0


def test_run_background_terminate() -> None:
    """Test terminating a background process."""
    proc = run_background(["sleep", "10"])

    # Process should be running
    time.sleep(0.1)
    assert not proc.is_finished()

    # Terminate it
    proc.terminate(force_kill_seconds=2.0)

    # Should be terminated now
    assert proc.is_finished()
    # Return code will be non-zero due to termination
    assert proc.returncode != 0


def test_run_background_wait_timeout() -> None:
    """Test that wait() properly times out."""
    proc = run_background(["sleep", "10"])

    start_time = time.time()
    with pytest.raises(TimeoutExpired):  # subprocess.TimeoutExpired
        proc.wait(timeout=0.5)

    elapsed = time.time() - start_time
    assert elapsed < 1.0  # Should timeout quickly

    # Process should still be running
    assert not proc.is_finished()

    # Clean up
    proc.terminate()


def test_run_background_with_cwd() -> None:
    """Test running background process in specific directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test files
        (tmpdir_path / "test1.txt").touch()
        (tmpdir_path / "test2.txt").touch()

        proc = run_background(["ls"], cwd=tmpdir_path)

        stdout, stderr = proc.wait_and_read(timeout=5.0)

        assert proc.returncode == 0
        assert "test1.txt" in stdout
        assert "test2.txt" in stdout


def test_run_background_non_zero_exit() -> None:
    """Test background process with non-zero exit code."""
    proc = run_background(["sh", "-c", "echo 'error message' >&2; exit 42"])

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 42
    assert stdout == ""
    assert stderr.strip() == "error message"


def test_run_background_non_zero_exit_with_checked_output() -> None:
    """Test background process with non-zero exit code."""
    proc = run_background(["sh", "-c", "echo 'error message' >&2; exit 42"], is_checked=True)
    with pytest.raises(ProcessError):
        proc.wait()

    stdout, stderr = proc.read_stdout(), proc.read_stderr()
    assert proc.returncode == 42
    assert stdout == ""
    assert stderr.strip() == "error message"


def test_run_background_command_not_found() -> None:
    """Test running a non-existent command."""
    with pytest.raises(ProcessSetupError):
        proc = run_background(["nonexistent_command_xyz123"])


def test_run_background_inner_thread_does_not_leak_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """SCU-1265: An unexpected exception in the inner subprocess-wrapper thread
    must not bubble out of ``threading.Thread`` uncaught.

    In the production trace, a workspace was deleted between message-queue and
    ``subprocess.Popen`` time. The Popen failure was wrapped into
    ``ProcessSetupError`` (which is silenced) and re-raised in the main thread.
    But the same code path can also see non-``OSError`` exceptions from the
    subprocess machinery (e.g. unexpected runtime errors mid-spawn) — those
    are NOT silenced by ``RunningProcess.start``'s ``silenced_exceptions``
    tuple, so the inner thread re-raises out of ``threading.Thread``. That
    triggers ``threading.excepthook`` and (per the ticket) leaves the
    enclosing concurrency group's "failed-strand" tracking in a state that
    wedges every subsequent strand-creation call.

    The fix wraps the inner thread body in ``try/except BaseException`` so
    the thread can never leak. The exception is still surfaced in the main
    thread via the ``on_initialization_complete`` callback (which fires
    inside ``call_on_exit`` before this code returns) and via ``poll()`` /
    ``wait()`` (which preserve the exception state on the thread).
    """
    sentinel = RuntimeError("simulated unexpected internal failure during subprocess spawn")

    def fake_run_local_command_modern_version(*_a: object, **_kw: object) -> NoReturn:
        # Fire the initialization callback BEFORE raising, mirroring how the
        # real ``call_on_exit`` context manager surfaces the exception to start().
        on_init = _kw.get("on_initialization_complete")
        if callable(on_init):
            on_init(sentinel)
        raise sentinel

    monkeypatch.setattr(local_process_module, "run_local_command_modern_version", fake_run_local_command_modern_version)

    captured: list[threading.ExceptHookArgs] = []

    def custom_excepthook(args: threading.ExceptHookArgs) -> None:
        captured.append(args)

    original_excepthook = threading.excepthook
    threading.excepthook = custom_excepthook
    try:
        with pytest.raises(RuntimeError, match="simulated unexpected internal failure"):
            run_background(["echo", "hi"])

        # Deterministically wait for the inner thread to finish unwinding,
        # rather than sleeping for a fixed duration.
        _join_inner_subprocess_threads()
    finally:
        threading.excepthook = original_excepthook

    leaked_summaries = [
        f"{args.exc_type.__name__}: {args.exc_value} in thread {args.thread.name if args.thread else '?'}"
        for args in captured
    ]
    assert not captured, f"Inner subprocess-wrapper thread leaked an exception to threading.excepthook (SCU-1265): {leaked_summaries}"


def test_run_background_inner_thread_runtime_failure_surfaced_by_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """SCU-1265: when the inner subprocess-wrapper thread raises AFTER Popen
    has succeeded (i.e. the initialization callback has already fired with
    ``None``), the exception is recorded on the ObservableThread so that
    ``poll()`` / ``wait()`` still surface it via ``maybe_raise()``.

    Before the SCU-1265 fix, the same surface was provided by
    ``ObservableThread.run``'s outer handler (which set ``_exception`` and
    then re-raised, causing ``threading.excepthook`` to fire). The fix moved
    the storage into ``RunningProcess.run`` via ``record_inner_exception``;
    this test pins down that the storage still happens and ``wait()`` still
    raises, so callers that rely on the failure surfacing aren't broken.
    """
    runtime_failure = RuntimeError("simulated runtime failure after popen succeeded")

    def fake_run_local_command_modern_version(*_a: object, **_kw: object) -> NoReturn:
        # Popen succeeded: fire the init callback with ``None`` so ``start()``
        # returns normally and the caller gets a ``RunningProcess`` handle.
        on_init = _kw.get("on_initialization_complete")
        if callable(on_init):
            on_init(None)
        # Then raise as if the streaming loop hit an unexpected error.
        raise runtime_failure

    monkeypatch.setattr(local_process_module, "run_local_command_modern_version", fake_run_local_command_modern_version)

    # ``start()`` should return normally because Popen "succeeded".
    proc = run_background(["echo", "runtime"])

    # ``wait()`` should surface the runtime failure via the recorded exception.
    with pytest.raises(RuntimeError, match="simulated runtime failure after popen succeeded"):
        proc.wait(timeout=INNER_THREAD_JOIN_TIMEOUT_SEC)


def test_run_background_shutdown_event() -> None:
    """Test using shutdown event to interrupt background process."""
    shutdown_event = Event()

    proc = run_background(["sleep", "10"], shutdown_event=shutdown_event, shutdown_timeout_sec=1.0)

    # Let it run briefly
    time.sleep(0.2)
    assert not proc.is_finished()

    # Trigger shutdown
    shutdown_event.set()

    # Wait for shutdown to complete
    time.sleep(1.5)

    # Process should be terminated
    assert proc.is_finished()
    assert proc.returncode != 0


def test_run_background_compound_shutdown_event() -> None:
    """Test using CompoundEvent for shutdown."""
    event1 = Event()
    event2 = Event()
    compound_event = CompoundEvent([event1, event2])

    # RemoteRunningProcess lets shutdown_event be a ReadOnlyEvent, including CompoundEvent, but RunningProcess only allows MutableEvent
    proc: RunningProcess = run_background(
        ["sleep", "10"],
        shutdown_event=compound_event,  # pyre-fixme[6]
        shutdown_timeout_sec=1.0,
    )

    # Let it run briefly
    time.sleep(0.2)
    assert not proc.is_finished()

    # Trigger one of the compound events
    event2.set()

    # Wait for shutdown
    time.sleep(1.5)

    # Process should be terminated
    assert proc.is_finished()
    assert proc.returncode != 0


def test_run_background_read_methods() -> None:
    """Test read_stdout and read_stderr methods."""
    proc = run_background(["sh", "-c", "echo 'stdout1'; echo 'stderr1' >&2; echo 'stdout2'; echo 'stderr2' >&2"])

    proc.wait(timeout=5.0)

    stdout = proc.read_stdout()
    stderr = proc.read_stderr()

    assert "stdout1" in stdout
    assert "stdout2" in stdout
    assert "stderr1" in stderr
    assert "stderr2" in stderr

    assert proc.returncode == 0


def test_run_background_get_queue() -> None:
    """Test get_queue method returns the correct queue."""
    custom_queue = Queue()
    proc = run_background(["echo", "test"], output_queue=custom_queue)

    # get_queue should return our custom queue
    assert proc.get_queue() is custom_queue

    proc.wait(timeout=5.0)

    # Output should be in our custom queue
    line, is_stdout = custom_queue.get(timeout=1.0)
    assert line == "test\n"
    assert is_stdout


def test_run_background_concurrent_processes() -> None:
    """Test running multiple background processes concurrently."""
    procs = []

    # Start multiple processes
    for i in range(3):
        proc = run_background(["sh", "-c", f"sleep 0.{i}; echo 'Process {i}'"])
        procs.append(proc)

    # Wait for all to complete
    results = []
    for i, proc in enumerate(procs):
        stdout, stderr = proc.wait_and_read(timeout=5.0)
        results.append((i, stdout.strip()))
        assert proc.returncode == 0

    # Verify all processes completed successfully
    for i, output in results:
        assert output == f"Process {i}"


def test_run_background_large_output() -> None:
    """Test handling of large output."""
    # Generate ~100KB of output
    proc = run_background(
        ["sh", "-c", 'for i in $(seq 1 2000); do echo "Line $i - This is a longer line to increase output size"; done']
    )

    stdout, stderr = proc.wait_and_read(timeout=10.0)

    assert proc.returncode == 0
    lines = stdout.strip().split("\n")
    assert len(lines) == 2000
    assert lines[0] == "Line 1 - This is a longer line to increase output size"
    assert lines[1999] == "Line 2000 - This is a longer line to increase output size"


def test_run_background_queue_ordering() -> None:
    """Test that queue preserves output order."""
    output_queue = Queue()

    proc = run_background(["sh", "-c", 'for i in 1 2 3 4 5; do echo "Line $i"; done'], output_queue=output_queue)

    proc.wait(timeout=5.0)

    # Read all lines from queue
    lines = []
    while not output_queue.empty():
        line, is_stdout = output_queue.get()
        if is_stdout:
            lines.append(line.strip())

    # Verify order
    assert len(lines) == 5
    for i in range(5):
        assert lines[i] == f"Line {i + 1}"


def test_run_background_empty_output() -> None:
    """Test process with no output."""
    proc = run_background(["true"])

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 0
    assert stdout == ""
    assert stderr == ""


def test_run_background_timeout_parameter() -> None:
    """Test that the timeout parameter is passed to the underlying process."""
    # This should timeout because sleep takes longer than timeout
    proc = run_background(["sleep", "10"], timeout=0.5)

    # The process should fail due to timeout
    start_time = time.time()
    return_code = proc.wait(timeout=2.0)
    elapsed = time.time() - start_time

    # Should have timed out quickly
    assert elapsed < 1.5
    assert return_code != 0


def test_run_background_trace_log_context() -> None:
    """Test that trace_log_context is passed through."""
    trace_context = {"request_id": "test-123", "user": "test_user"}

    proc = run_background(["echo", "test with context"], trace_log_context=trace_context)

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 0
    assert stdout.strip() == "test with context"


def test_run_background_interleaved_stdout_stderr() -> None:
    """Test that stdout and stderr maintain their order in the queue."""
    output_queue = Queue()

    # Command that interleaves stdout and stderr
    proc = run_background(
        ["sh", "-c", "echo 'out1'; echo 'err1' >&2; echo 'out2'; echo 'err2' >&2"], output_queue=output_queue
    )

    proc.wait(timeout=5.0)

    # Collect all output
    output = []
    while not output_queue.empty():
        line, is_stdout = output_queue.get()
        output.append((line.strip(), is_stdout))

    assert len(output) == 4
    # Check we got the expected lines (order might vary slightly due to buffering)
    stdout_lines = [line for line, is_stdout in output if is_stdout]
    stderr_lines = [line for line, is_stdout in output if not is_stdout]

    assert sorted(stdout_lines) == ["out1", "out2"]
    assert sorted(stderr_lines) == ["err1", "err2"]


def test_run_background_partial_line_handling() -> None:
    """Test handling of output without trailing newlines."""
    output_queue = Queue()

    # Command that outputs without newline at the end
    proc = run_background(["sh", "-c", "printf 'no newline'"], output_queue=output_queue)

    stdout, stderr = proc.wait_and_read(timeout=5.0)

    assert proc.returncode == 0
    assert stdout == "no newline"

    queue_items = []
    while not output_queue.empty():
        queue_items.append(output_queue.get())

    # If there are items, verify they're correct
    assert len(queue_items) == 1
    line, is_stdout = queue_items[0]
    assert "no newline" in line


def test_run_background_thread_safety() -> None:
    """Test that RunningProcess is thread-safe for concurrent access."""
    proc = run_background(["sh", "-c", "for i in 1 2 3; do echo $i; sleep 0.1; done"])

    results = {"poll": [], "is_finished": [], "stdout": [], "stderr": []}
    errors = []

    def poll_thread() -> None:
        try:
            for _ in range(10):
                results["poll"].append(proc.poll())
                time.sleep(0.05)
        except Exception as e:
            errors.append(e)

    def check_thread() -> None:
        try:
            for _ in range(10):
                results["is_finished"].append(proc.is_finished())
                time.sleep(0.05)
        except Exception as e:
            errors.append(e)

    def read_thread() -> None:
        try:
            for _ in range(5):
                results["stdout"].append(proc.read_stdout())
                results["stderr"].append(proc.read_stderr())
                time.sleep(0.1)
        except Exception as e:
            errors.append(e)

    # Start threads
    threads = [
        threading.Thread(target=poll_thread),
        threading.Thread(target=check_thread),
        threading.Thread(target=read_thread),
    ]

    for t in threads:
        t.start()

    # Wait for process and threads
    proc.wait(timeout=5.0)

    for t in threads:
        t.join()

    # Check no errors occurred
    assert len(errors) == 0
    assert proc.returncode == 0


def test_run_background_shutdown_event_already_set() -> None:
    shutdown_event = Event()
    shutdown_event.set()
    proc = run_background(["sleep", "10"], shutdown_event=shutdown_event)
    proc.wait(timeout=2.0)
    assert proc.is_finished()
    assert proc.returncode != 0
