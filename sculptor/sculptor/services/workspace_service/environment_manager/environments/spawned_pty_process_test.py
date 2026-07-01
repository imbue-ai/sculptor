"""Tests for SpawnedPtyProcess.

These run a real ``os.posix_spawn`` helper subprocess plus a real shell
on the developer's machine, so they cover the full
backend -> posix_spawn -> pty_helper -> pty.fork -> shell path.
"""

import os
import select
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


@pytest.fixture(autouse=True)
def _isolate_shell_config(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point the spawned login shell at an empty HOME/ZDOTDIR so it sources no
    user rc files.

    These tests spawn a real ``$SHELL -l`` — a login shell, which sources the
    user's full rc chain. Left alone, that turns the developer's personal
    terminal configuration (prompt themes, plugins, syntax highlighting,
    bracketed-paste) into uncontrolled test input — a bare ``/bin/bash`` on CI
    behaves nothing like a heavily-themed zsh on a laptop. Pointing HOME (bash,
    ``~/.profile`` etc.) and ZDOTDIR (zsh, ``.zshrc`` etc.) at an empty
    directory gives every run a vanilla prompt, so what the tests observe
    depends only on Sculptor's own env handling, not on who runs the suite.
    """
    empty_home = tmp_path_factory.mktemp("empty_shell_home")
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("ZDOTDIR", str(empty_home))


# Sentinels bracketing the echoed value. We search for the fully-expanded form
# (e.g. ``<SCT|local_port_5050|SCT>``), which can appear ONLY in the command's
# OUTPUT: the shell's echo of the *typed* command still has the literal
# ``${VAR}`` between the sentinels, so it can never match — not even for an
# empty (scrubbed) value, whose output is ``<SCT||SCT>``. That is what lets the
# scrub assertions prove a variable is genuinely empty in the child, instead of
# passing on any substring that merely happens to appear on the line (such as
# the shell's own echo of the typed command).
_SENTINEL_OPEN = "<SCT|"
_SENTINEL_CLOSE = "|SCT>"


@contextmanager
def _running_pty(proc: SpawnedPtyProcess) -> Generator[int, None, None]:
    """Start a SpawnedPtyProcess, yield its primary fd, and ensure cleanup.

    There is deliberately no fixed "wait for the prompt" sleep here:
    ``_assert_pty_echo`` resends its probe until the shell is actually ready,
    which is robust to a slow login-shell init under load. A fixed pre-write
    delay is unreliable — a heavily-configured shell (plugins, async/instant
    prompt) can still be initializing, and dropping typed-ahead input, well past
    any hardcoded delay.
    """
    proc.start()
    try:
        fd = proc.primary_fd
        assert fd is not None
        yield fd
    finally:
        try:
            proc.terminate(force_kill_seconds=1.0)
        except BaseException:
            pass
        proc.close_primary_fd()


def _assert_pty_echo(fd: int, env_var: str, expected: str, timeout: float = 15.0) -> None:
    """Echo ``$env_var`` through the pty and assert its value equals ``expected``.

    The probe command is *resent* periodically rather than written once after a
    fixed delay: an interactive login shell with a heavy rc (prompt plugins,
    async/instant prompt, syntax highlighting) can still be initializing — and
    discarding typed-ahead input — for a second or more after it first draws a
    prompt, especially when several shells start at once under parallel-test
    load. Resending guarantees at least one probe lands once the shell is ready,
    instead of betting that init finished within a hardcoded window.

    The sentinels bracket the value so a match can come only from the command's
    output (never the shell's echo of the typed command), which keeps the
    assertion meaningful even for an empty value. The expanded sentinel string
    lands contiguously on echo's output line, so a plain substring search over
    the raw bytes suffices — no escape-stripping needed once the shell is
    isolated to a vanilla config (see ``_isolate_shell_config``).
    """
    marker = f"{_SENTINEL_OPEN}{expected}{_SENTINEL_CLOSE}".encode()
    command = f'echo "{_SENTINEL_OPEN}${{{env_var}}}{_SENTINEL_CLOSE}"\n'.encode()

    # Wait for readability with poll(2), not select(2): select cannot wait on a
    # file descriptor whose number is >= FD_SETSIZE (1024) and raises
    # "filedescriptor out of range in select()". An fd-heavy test run (xdist, a
    # long-lived process) can hand a freshly opened pty a high fd number, so a
    # select() here would reintroduce exactly the high-fd flakiness the
    # production reader uses poll(2) to avoid.
    poller = select.poll()
    poller.register(fd, select.POLLIN)

    output = b""
    deadline = time.monotonic() + timeout
    next_send = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_send:
            try:
                os.write(fd, command)
            except OSError:
                pass
            next_send = now + 0.75
        # poll so we never block past the resend cadence; the pty primary fd is
        # non-blocking, so a bare os.read would spin on BlockingIOError. A 200ms
        # timeout (in milliseconds for poll) paces the loop when there is no data.
        if not poller.poll(200):
            continue
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            continue
        except OSError:
            break  # EIO/EBADF: the shell is gone; stop and report what we have.
        if not chunk:
            break  # EOF: the shell exited.
        output += chunk
        if marker in output:
            return
    raise AssertionError(
        f"marker {marker!r} for ${env_var} not seen within {timeout:.0f}s; output: {output.decode(errors='replace')!r}"
    )


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


# ``_scrub_shell_env`` is the pure function that actually decides what the shell
# sees; the pty echo tests above prove a value survives an end-to-end spawn,
# while these pin down every branch of the rule deterministically — no pty, no
# shell, no dependence on the developer's terminal at all.


def test_scrub_shell_env_removes_sculptor_internal_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCULPT_API_PORT", "5050")
    monkeypatch.setenv("SCULPTOR_INTERNAL", "x")
    monkeypatch.setenv("_PYI_BOOTSTRAP", "x")
    monkeypatch.setenv("SESSION_TOKEN", "secret")
    monkeypatch.setenv("SCTEST_UNRELATED", "keep")

    env = spawned_pty_process._scrub_shell_env(extra_env={}, env_var_override=False)

    assert "SCULPT_API_PORT" not in env
    assert "SCULPTOR_INTERNAL" not in env
    assert "_PYI_BOOTSTRAP" not in env
    assert "SESSION_TOKEN" not in env
    # Vars outside the excluded names/prefixes are left untouched.
    assert env["SCTEST_UNRELATED"] == "keep"
    # The pty advertises xterm-256color, so TERM is always forced to match.
    assert env["TERM"] == spawned_pty_process.TERMINAL_TYPE


def test_scrub_shell_env_injects_extra_env_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCTEST_NEW_VAR", raising=False)
    env = spawned_pty_process._scrub_shell_env(extra_env={"SCTEST_NEW_VAR": "new"}, env_var_override=False)
    assert env["SCTEST_NEW_VAR"] == "new"


def test_scrub_shell_env_keeps_inherited_value_when_override_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCTEST_EXISTING", "original")
    env = spawned_pty_process._scrub_shell_env(extra_env={"SCTEST_EXISTING": "replacement"}, env_var_override=False)
    assert env["SCTEST_EXISTING"] == "original"


def test_scrub_shell_env_replaces_inherited_value_when_override_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCTEST_EXISTING", "original")
    env = spawned_pty_process._scrub_shell_env(extra_env={"SCTEST_EXISTING": "replacement"}, env_var_override=True)
    assert env["SCTEST_EXISTING"] == "replacement"


def test_scrub_shell_env_prepends_path_even_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    # PATH is special-cased: a terminal's extra PATH is *prepended* (so its tools
    # win) rather than replacing the inherited PATH — and this happens even with
    # override disabled, unlike every other key.
    env = spawned_pty_process._scrub_shell_env(extra_env={"PATH": "/custom/bin"}, env_var_override=False)
    assert env["PATH"] == "/custom/bin" + os.pathsep + "/usr/bin"


def test_scrub_shell_env_reinjects_scrubbed_sculpt_var(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Sculptor-on-Sculptor case (see test_inherited_sculpt_env_... above),
    # isolated to the pure function: the inherited SCULPT_* value is scrubbed, so
    # extra_env's fresh value is injected and wins even with override disabled —
    # precisely because scrubbing removed the inherited one first.
    monkeypatch.setenv("SCULPT_API_PORT", "outer_port_12345")
    env = spawned_pty_process._scrub_shell_env(
        extra_env={"SCULPT_API_PORT": "local_port_5050"}, env_var_override=False
    )
    assert env["SCULPT_API_PORT"] == "local_port_5050"


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
