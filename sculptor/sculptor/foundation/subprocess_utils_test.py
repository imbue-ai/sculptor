import signal
import subprocess
import time
from threading import Event
from threading import Thread

import pytest

from sculptor.foundation.processes.posix_spawn_process import LocalProcessHandle
from sculptor.foundation.processes.posix_spawn_process import PosixSpawnedProcess
from sculptor.foundation.subprocess_utils import CommandError
from sculptor.foundation.subprocess_utils import SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE
from sculptor.foundation.subprocess_utils import run_local_command
from sculptor.foundation.subprocess_utils import run_local_command_modern_version


def send_stop(event: Event) -> None:
    time.sleep(2)
    event.set()


def test_run_local_command_respects_shutdown_event() -> None:
    start_time = time.time()
    event = Event()
    thread = Thread(target=send_stop, args=(event,))
    thread.start()
    try:
        run_local_command("sleep 10", shutdown_event=event)
    except CommandError as e:
        assert e.returncode == SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE
    thread.join(1)
    assert event.is_set()
    assert not thread.is_alive()
    assert time.time() - start_time < 5


def test_run_local_command_gets_stdout_output() -> None:
    res = run_local_command("echo test")
    assert res.stdout == b"test\n"
    assert res.stdout_str == "test\n"
    assert res.stderr == b""
    assert res.stderr_str == ""
    assert res.output == "test\n"


def test_run_local_command_gets_stderr_output() -> None:
    res = run_local_command(">&2 echo test")
    assert res.stdout == b""
    assert res.stdout_str == ""
    assert res.stderr == b"test\n"
    assert res.stderr_str == "test\n"
    assert res.output == "test\n"


def test_run_local_command_gets_both_output() -> None:
    res = run_local_command("echo test; >&2 echo test")
    assert res.stdout == b"test\n"
    assert res.stdout_str == "test\n"
    assert res.stderr == b"test\n"
    assert res.stderr_str == "test\n"
    assert res.output == "test\ntest\n"


def test_run_local_command_raises_by_default() -> None:
    with pytest.raises(CommandError):
        run_local_command("exit 1")


def test_run_local_command_doesnt_raise_when_not_is_checked() -> None:
    result = run_local_command("exit 1", is_checked=False)
    assert result.returncode == 1, "run_local_command should not raise when is_checked=False"


def test_check_already_populated_failure() -> None:
    result = run_local_command("echo foo; exit 1", is_checked=False)
    assert result.stdout == b"foo\n"
    assert result.stdout_str == "foo\n"
    assert result.stderr == b""
    assert result.stderr_str == ""
    assert result.output == "foo\n"

    with pytest.raises(CommandError) as e:
        result.check()

    # The exception should use the _already populated_ output.
    assert e.value.output is result.output


def test_run_local_command_modern_version_closes_output_pipes() -> None:
    """The stdout/stderr pipe fds must be closed once output is gathered, rather
    than left open until the Popen is garbage-collected.

    Background processes retain the live Popen on ``RunningProcess`` (captured
    via ``on_popen_ready``), and the finished ``RunningProcess`` lingers on its
    ``ConcurrencyGroup`` until a periodic cleanup tick — so without an explicit
    close the two pipe fds would leak well past process exit. We grab the live
    Popen through ``on_popen_ready`` and assert both pipes are closed after the
    call returns.
    """
    captured: list[LocalProcessHandle] = []
    result = run_local_command_modern_version(
        ["echo", "hello"],
        on_popen_ready=captured.append,
    )

    assert result.stdout == "hello\n"
    assert len(captured) == 1
    process = captured[0]
    assert process.stdout is not None and process.stdout.closed, "stdout pipe was left open after the command finished"
    assert process.stderr is not None and process.stderr.closed, "stderr pipe was left open after the command finished"


def test_run_local_command_modern_version_posix_spawn_captures_output_and_closes_pipes() -> None:
    """The posix_spawn path drives the same delicate output/cleanup loop as Popen.

    With ``prefer_posix_spawn=True`` (and ``cwd`` None) the command must actually be
    spawned via ``os.posix_spawn`` — we assert the handle is a ``PosixSpawnedProcess``,
    not a Popen — yet stdout is still captured and the pipe fds are closed afterward,
    exactly like the Popen path tested above.
    """
    captured: list[LocalProcessHandle] = []
    result = run_local_command_modern_version(
        ["echo", "hello"],
        prefer_posix_spawn=True,
        on_popen_ready=captured.append,
    )

    assert result.stdout == "hello\n"
    assert len(captured) == 1
    process = captured[0]
    assert isinstance(process, PosixSpawnedProcess), "prefer_posix_spawn=True must route through posix_spawn"
    assert process.stdout is not None and process.stdout.closed, "stdout pipe was left open after the command finished"
    assert process.stderr is not None and process.stderr.closed, "stderr pipe was left open after the command finished"


def test_isolation_request_routes_through_popen_not_posix_spawn() -> None:
    """Process-group isolation must use Popen, even when posix_spawn is preferred.

    The posix_spawn primitive deliberately does not implement isolation
    (``start_new_session``/``setsid``), so a command requesting it must fall back
    to ``subprocess.Popen`` (whose ``start_new_session=True`` is portable) rather
    than silently spawn a non-isolated child. Output must still be captured.
    """
    captured: list[LocalProcessHandle] = []
    result = run_local_command_modern_version(
        ["echo", "hello"],
        prefer_posix_spawn=True,
        isolate_process_group=True,
        on_popen_ready=captured.append,
    )

    assert result.stdout == "hello\n"
    assert len(captured) == 1
    assert isinstance(captured[0], subprocess.Popen), "isolation must route through Popen, not posix_spawn"


def test_run_local_command_modern_version_posix_spawn_shutdown_terminates() -> None:
    """A shutdown_event must promptly stop a long-running posix_spawn child, going
    through the same SIGTERM shutdown path Popen uses (``_shutdown_popen`` →
    ``send_shutdown_signal`` → the handle's ``terminate``/``wait``)."""
    shutdown_event = Event()
    thread = Thread(target=send_stop, args=(shutdown_event,))
    thread.start()
    start_time = time.time()

    result = run_local_command_modern_version(
        ["sleep", "30"],
        prefer_posix_spawn=True,
        is_checked=False,
        shutdown_event=shutdown_event,
    )

    thread.join(1)
    elapsed_time = time.time() - start_time
    # sleep installs no SIGTERM handler, so it dies on the signal: negative returncode.
    assert result.returncode == -signal.SIGTERM
    assert elapsed_time < 5, f"Process took {elapsed_time:.2f}s, expected the shutdown to interrupt it"


def test_run_local_command_timeout_stops_long_running_process() -> None:
    start_time = time.time()

    # Use a shutdown event that will be set after 2 seconds to simulate timeout
    shutdown_event = Event()
    thread = Thread(target=send_stop, args=(shutdown_event,))
    thread.start()

    try:
        # This command would normally run for 10 seconds, but should be stopped after ~2 seconds
        run_local_command("sleep 10", shutdown_event=shutdown_event, is_checked=True)
        assert False, "Expected CommandError to be raised"
    except CommandError as e:
        # Should be stopped by the shutdown event
        assert e.returncode == SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE

    thread.join(1)
    elapsed_time = time.time() - start_time

    # Verify the process was stopped early (should be ~2 seconds, not 10)
    assert elapsed_time < 5, f"Process took {elapsed_time:.2f}s, expected < 5s"
    assert elapsed_time > 1.5, f"Process took {elapsed_time:.2f}s, expected > 1.5s"
