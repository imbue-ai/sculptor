"""Tests for SpawnedPtyProcess.

These run a real ``os.posix_spawn`` helper subprocess plus a real shell
on the developer's machine, so they cover the full
backend -> posix_spawn -> pty_helper -> pty.fork -> shell path.
"""

import os
import signal
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest

from sculptor.services.workspace_service.environment_manager.environments import spawned_pty_process
from sculptor.services.workspace_service.environment_manager.environments.spawned_pty_process import (
    PtyHelperSpawnError,
)
from sculptor.services.workspace_service.environment_manager.environments.spawned_pty_process import SpawnedPtyProcess

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


def _read_pty_until(fd: int, marker: str, timeout: float = 5.0) -> str:
    """Read from pty fd until marker appears or timeout expires."""
    output = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = os.read(fd, 4096)
            if chunk:
                output += chunk
                if marker.encode() in output:
                    return output.decode(errors="replace")
        except OSError:
            pass
        time.sleep(0.05)
    return output.decode(errors="replace")


@contextmanager
def _running_pty(proc: SpawnedPtyProcess) -> Generator[int, None, None]:
    """Start a SpawnedPtyProcess, yield its primary fd, and ensure cleanup."""
    proc.start()
    try:
        # Give the shell a moment to print its prompt before we write commands.
        time.sleep(0.5)
        fd = proc.primary_fd
        assert fd is not None
        yield fd
    finally:
        try:
            proc.terminate(force_kill_seconds=1.0)
        except BaseException:
            pass
        proc.close_primary_fd()


def _assert_pty_echo(fd: int, env_var: str, expected: str) -> None:
    """Write an echo command to the pty and assert the output contains the marker."""
    marker = f"CHECK:{expected}"
    os.write(fd, f'echo "CHECK:${{{env_var}}}"\n'.encode())
    output = _read_pty_until(fd, marker)
    assert marker in output


def test_extra_env_available_in_child(tmp_path: Path) -> None:
    proc = SpawnedPtyProcess(
        name="test-env",
        working_directory=tmp_path,
        extra_env={"SCTEST_PTY_UNIQUE": "pty_42xyz"},
    )
    with _running_pty(proc) as fd:
        _assert_pty_echo(fd, "SCTEST_PTY_UNIQUE", "pty_42xyz")


def test_extra_env_no_override_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCTEST_EXISTING_VAR", "original_val")
    proc = SpawnedPtyProcess(
        name="test-no-override",
        working_directory=tmp_path,
        extra_env={"SCTEST_EXISTING_VAR": "should_not_win"},
        env_var_override=False,
    )
    with _running_pty(proc) as fd:
        _assert_pty_echo(fd, "SCTEST_EXISTING_VAR", "original_val")


def test_extra_env_overrides_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCTEST_OV_VAR", "old_value")
    proc = SpawnedPtyProcess(
        name="test-override",
        working_directory=tmp_path,
        extra_env={"SCTEST_OV_VAR": "new_value"},
        env_var_override=True,
    )
    with _running_pty(proc) as fd:
        _assert_pty_echo(fd, "SCTEST_OV_VAR", "new_value")


def test_inherited_sculpt_env_is_scrubbed_so_extra_env_takes_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sculptor-on-Sculptor: inherited SCULPT_* values must be scrubbed
    before extra_env injects the local backend's fresh values, otherwise
    the inner ``sculpt`` CLI would phone home to the outer backend.
    """
    monkeypatch.setenv("SCULPT_API_PORT", "outer_port_12345")
    monkeypatch.setenv("SCULPT_AGENT_ID", "outer_agent_id")
    monkeypatch.setenv("SCULPT_LEAKED_VAR", "should_not_be_visible")
    proc = SpawnedPtyProcess(
        name="test-scrub-sculpt",
        working_directory=tmp_path,
        extra_env={"SCULPT_API_PORT": "local_port_5050"},
        env_var_override=False,
    )
    with _running_pty(proc) as fd:
        _assert_pty_echo(fd, "SCULPT_API_PORT", "local_port_5050")
        _assert_pty_echo(fd, "SCULPT_AGENT_ID", "")
        _assert_pty_echo(fd, "SCULPT_LEAKED_VAR", "")


def test_shell_exit_via_close_primary_fd_is_detected(tmp_path: Path) -> None:
    """Closing the primary fd delivers SIGHUP to the shell, which an
    interactive login shell honors and exits in response.  The backend
    detects the death by polling ``os.kill(shell_pid, 0)``.
    """
    proc = SpawnedPtyProcess(name="test-sighup", working_directory=tmp_path)
    proc.start()
    try:
        proc.close_primary_fd()
        rc = proc.wait(timeout=5.0)
        assert rc is not None
        assert proc.is_finished()
    finally:
        try:
            proc.terminate(force_kill_seconds=1.0)
        except BaseException:
            pass


def test_close_primary_fd_then_terminate_kills_shell(tmp_path: Path) -> None:
    """``LocalTerminalManager.stop`` calls ``close_primary_fd()`` *before*
    ``terminate()``: closing the backend's last reference to the pty primary
    side is what lets the kernel deliver SIGHUP and finish tearing down the
    session leader.  Without it, the shell can sit in macOS's ``E`` (exiting,
    holding ctty) state for several seconds even after SIGKILL.  This test
    exercises the production teardown order.

    The helper subprocess is already reaped by the time ``start()`` returns,
    so this test only checks the shell pid -- which is now an orphan that
    init reaps once it exits.
    """
    proc = SpawnedPtyProcess(name="test-terminate", working_directory=tmp_path)
    proc.start()
    try:
        time.sleep(0.5)
        assert proc._helper is not None
        shell_pid = proc._helper.shell_pid

        proc.close_primary_fd()
        proc.terminate(force_kill_seconds=2.0)

        deadline = time.monotonic() + 2.0
        shell_dead = False
        while time.monotonic() < deadline and not shell_dead:
            try:
                os.kill(shell_pid, 0)
            except ProcessLookupError:
                shell_dead = True
            time.sleep(0.02)
        assert shell_dead, f"shell pid {shell_pid} still alive after teardown"
    finally:
        proc.close_primary_fd()


def test_unknown_shell_does_not_hang_backend(tmp_path: Path) -> None:
    """An unresolvable shell must not hang the backend.

    The helper's grandchild exits with 127 from execvpe(FileNotFoundError),
    but the helper-parent has already sent ``("ok", pid)`` + the fd before
    the grandchild's exit is observed (the typed-status-first ordering).
    So ``start()`` succeeds, and the next ``wait()`` call observes the shell
    has died (the grandchild's immediate exec failure means the shell pid
    disappears almost instantly).
    """
    proc = SpawnedPtyProcess(
        name="test-bad-shell",
        working_directory=tmp_path,
        shell="/definitely/does/not/exist/sculptor_test_shell",
    )
    proc.start()
    try:
        rc = proc.wait(timeout=5.0)
        assert rc is not None
        assert proc.is_finished()
    finally:
        proc.close_primary_fd()


def test_helper_failure_to_import_raises_spawn_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the helper can't even import, start() should raise rather than hang.

    The helper subprocess exits immediately. Depending on scheduling, the
    backend may observe the death either as EOF on the recv side
    (_await_ok_and_fd) or as EPIPE on the send side of the config blob
    (_send_config); both must surface as PtyHelperSpawnError rather than
    a bare BrokenPipeError/EOFError leaking out of multiprocessing.
    """
    bad_executable = tmp_path / "not_a_python.sh"
    bad_executable.write_text("#!/bin/sh\nexit 9\n")
    bad_executable.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(bad_executable))

    proc = SpawnedPtyProcess(name="test-bad-helper", working_directory=tmp_path)
    with pytest.raises(PtyHelperSpawnError):
        proc.start()


def test_concurrent_spawns_are_independent(tmp_path: Path) -> None:
    """Multiple SpawnedPtyProcess instances run concurrently and don't share state.

    Distinct shell pids, distinct primary fds.  Helpers are already reaped
    by the time each ``start()`` returns, so we can't compare helper pids
    -- the test asserts shell-side isolation, which is what callers see.
    """
    procs = [SpawnedPtyProcess(name=f"test-concurrent-{i}", working_directory=tmp_path) for i in range(3)]
    try:
        for proc in procs:
            proc.start()
        helpers = [proc._helper for proc in procs]
        for h in helpers:
            assert h is not None
        shell_pids = {h.shell_pid for h in helpers if h is not None}
        primary_fds = {h.primary_fd for h in helpers if h is not None}
        assert len(shell_pids) == len(procs)
        assert len(primary_fds) == len(procs)
    finally:
        for proc in procs:
            try:
                proc.terminate(force_kill_seconds=1.0)
            except BaseException:
                pass
            proc.close_primary_fd()


def test_signal_termination_is_detected(tmp_path: Path) -> None:
    """SIGKILL'ing the shell directly should be observed by ``wait()``.

    We no longer learn the exact exit code (no helper parked in
    ``waitpid``), but ``wait()`` must still return a non-None value once
    the shell is gone.
    """
    proc = SpawnedPtyProcess(name="test-sigkill", working_directory=tmp_path)
    proc.start()
    try:
        assert proc._helper is not None
        os.kill(proc._helper.shell_pid, signal.SIGKILL)
        rc = proc.wait(timeout=5.0)
        assert rc is not None
    finally:
        proc.close_primary_fd()


def test_helper_subprocess_is_reaped_by_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper exits after the SCM_RIGHTS handoff; ``_spawn_helper``
    reaps it before returning so we don't accumulate zombies.

    Captures the helper pid by wrapping ``_spawn_helper_subprocess`` and
    then asserts the pid no longer exists after ``start()``.
    """
    captured_helper_pids: list[int] = []
    real_spawn = spawned_pty_process._spawn_helper_subprocess

    def capturing_spawn(child_sock: socket.socket) -> int:
        helper_pid = real_spawn(child_sock)
        captured_helper_pids.append(helper_pid)
        return helper_pid

    monkeypatch.setattr(spawned_pty_process, "_spawn_helper_subprocess", capturing_spawn)

    proc = SpawnedPtyProcess(name="test-reap", working_directory=tmp_path)
    proc.start()
    try:
        assert len(captured_helper_pids) == 1
        helper_pid = captured_helper_pids[0]
        # After start() returns, the helper has been reaped. ``os.kill(pid, 0)``
        # may still see the pid for a brief window if the kernel hasn't fully
        # released it; poll for up to 1s.
        deadline = time.monotonic() + 1.0
        helper_gone = False
        while time.monotonic() < deadline:
            try:
                os.kill(helper_pid, 0)
            except ProcessLookupError:
                helper_gone = True
                break
            time.sleep(0.01)
        assert helper_gone, f"helper pid {helper_pid} not reaped by start()"
    finally:
        proc.close_primary_fd()
        try:
            proc.terminate(force_kill_seconds=1.0)
        except BaseException:
            pass
