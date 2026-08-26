"""Tests for the close-terminal lifecycle on LocalTerminalManager.

Exercises the unregister_terminal_manager + manager.stop() pair that backs
the DELETE /api/v1/workspaces/{id}/terminal/{index} HTTP route. Goes
through the real ConcurrencyGroup and a real pty so we observe the
actual shell pid going away.
"""

import errno
import os
import pty
import resource
import sys
import threading
import time
from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    LocalTerminalManager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    make_terminal_id,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.spawned_pty_process import SpawnedPtyProcess

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


@pytest.fixture(autouse=True)
def _isolate_shell_config(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point the spawned login shell at an empty HOME/ZDOTDIR so it sources no
    user rc files.

    These tests start a real terminal (``$SHELL -l``), and the self-exit test
    drives that shell to exit. A heavily-configured login shell is slow to
    initialize and drops typed-ahead input while it does, so a write issued
    right after start() can be lost — and how long that takes varies per
    developer. An empty HOME/ZDOTDIR gives every run a vanilla, fast-starting
    shell, so the behavior under test depends on Sculptor, not on who runs the
    suite.
    """
    empty_home = tmp_path_factory.mktemp("empty_shell_home")
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("ZDOTDIR", str(empty_home))


def _wait_for_dead(pid: int, timeout: float = 1.0) -> bool:
    """Return True once ``os.kill(pid, 0)`` raises ProcessLookupError.

    ``manager.stop()`` is synchronous, so the pid should already be reaped
    by the time this is called; the polling tail just covers the brief
    kernel-reap window with 5ms ticks.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.005)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
    return False


def test_unregister_and_stop_kills_shell(tmp_path: Path) -> None:
    environment_id = "env-close-test"
    terminal_id = make_terminal_id(environment_id, 0)
    with ConcurrencyGroup(name="terminal-close-test") as group:
        manager = LocalTerminalManager(
            environment_id=environment_id,
            terminal_index=0,
            workspace_path=tmp_path,
            working_directory=tmp_path,
            concurrency_group=group,
        )
        manager.start()
        register_terminal_manager(terminal_id, manager)
        try:
            assert get_terminal_manager(terminal_id) is manager
            assert manager._pty_process is not None
            helper = manager._pty_process._helper
            assert helper is not None
            shell_pid = helper.shell_pid
            assert shell_pid > 0
            # Shell is alive right now.
            os.kill(shell_pid, 0)

            removed = unregister_terminal_manager(terminal_id)
            assert removed is manager
            assert get_terminal_manager(terminal_id) is None

            manager.stop()
            assert _wait_for_dead(shell_pid), f"shell pid {shell_pid} still alive after stop()"
        finally:
            try:
                manager.stop()
            except BaseException:
                pass
            unregister_terminal_manager(terminal_id)


def test_unregister_missing_returns_none() -> None:
    assert unregister_terminal_manager("nonexistent-terminal-id") is None


def test_read_loop_closes_primary_fd_and_unregisters_on_shell_self_exit(tmp_path: Path) -> None:
    """When the shell exits on its own (e.g. the user types ``exit``), the reader
    thread must tear the terminal down itself — close the pty primary fd and
    unregister the manager.

    stop() only runs on an explicit user action (closing the panel) or workspace
    teardown, so without this every self-exited shell leaks one pty primary fd
    until then. Here we drive a real login shell to exit and assert the backend's
    primary fd is genuinely closed (``os.fstat`` raises EBADF) and the manager is
    no longer in the registry.
    """
    environment_id = "env-self-exit-test"
    terminal_id = make_terminal_id(environment_id, 0)
    with ConcurrencyGroup(name="terminal-self-exit-test") as group:
        manager = LocalTerminalManager(
            environment_id=environment_id,
            terminal_index=0,
            workspace_path=tmp_path,
            working_directory=tmp_path,
            concurrency_group=group,
        )
        manager.start()
        register_terminal_manager(terminal_id, manager)
        try:
            pty_process = manager._pty_process
            assert pty_process is not None
            assert pty_process._helper is not None
            primary_fd = pty_process._helper.primary_fd
            # The primary fd is open right now.
            os.fstat(primary_fd)

            # Tell the login shell to exit on its own. The reader thread should
            # then observe EOF/EIO and run the self-exit cleanup path, which
            # clears _pty_process once it has closed the fd + terminated the
            # shell (manager.stop() is never called here).
            #
            # ``exit`` is resent periodically rather than written once: a login
            # shell with a heavy rc can still be initializing — and discarding
            # typed-ahead input — right after start(), so a single early write
            # can be dropped and the shell would never exit. Resending until the
            # reader tears the terminal down makes this robust under load.
            #
            # Write straight to the captured pty fd rather than via
            # ``manager.write()``: the reader thread is concurrently nulling
            # ``manager._pty_process`` as it tears down, and ``write()`` reads
            # that attribute twice, so a resend racing the teardown could hit an
            # AttributeError. ``pty_process`` is a stable reference and its
            # ``primary_fd`` property reads cleanly (returning None once closed).
            deadline = time.monotonic() + 15.0
            next_write = 0.0
            while time.monotonic() < deadline and manager._pty_process is not None:
                now = time.monotonic()
                if now >= next_write:
                    exit_fd = pty_process.primary_fd
                    if exit_fd is not None:
                        try:
                            os.write(exit_fd, b"exit\n")
                        except OSError:
                            pass  # fd closed mid-teardown; the shell is already exiting
                    next_write = now + 0.5
                time.sleep(0.02)

            assert manager._pty_process is None, "reader did not tear down the pty after the shell self-exited"
            assert pty_process._is_primary_fd_closed, "primary fd was not closed after the shell self-exited"
            assert get_terminal_manager(terminal_id) is None, (
                "manager was not unregistered after the shell self-exited"
            )

            # The captured fd number is genuinely closed now.
            with pytest.raises(OSError) as exc_info:
                os.fstat(primary_fd)
            assert exc_info.value.errno == errno.EBADF
        finally:
            try:
                manager.stop()
            except BaseException:
                pass
            unregister_terminal_manager(terminal_id)


# A file descriptor number at or above FD_SETSIZE (1024).  select(2) — and
# therefore ``select.select()`` — cannot wait on an fd this high and raises
# ``ValueError: filedescriptor out of range in select()``.
_HIGH_FD = 1100


class _HighFdPtyProcess(SpawnedPtyProcess):
    """A SpawnedPtyProcess whose ``primary_fd`` is a caller-supplied fd.

    Constructing the base does not spawn anything (that happens in ``start()``),
    so this lets us point ``_read_loop`` at a pty fd we have deliberately placed
    at a high number without launching a real shell. ``_read_loop`` only reads
    ``primary_fd``, which we override here.
    """

    def __init__(self, primary_fd: int) -> None:
        super().__init__(name="test-high-fd", working_directory=Path("/"))
        self._test_primary_fd = primary_fd

    @property
    def primary_fd(self) -> int | None:
        return self._test_primary_fd


def test_read_loop_reads_from_high_numbered_fd(tmp_path: Path) -> None:
    """The pty reader must keep working when the primary fd is >= 1024.

    A long-lived backend steadily accumulates open fds; eventually a freshly
    opened pty is handed a fd number at or above FD_SETSIZE (1024).
    ``select.select()`` raises "filedescriptor out of range in select()" for
    such fds, which killed the reader thread the instant the terminal opened
    and surfaced to the user as "failing to open new terminals". This forces a
    real pty's primary fd onto a high number and asserts shell output still
    reaches subscribers.
    """
    # Raise the soft fd limit so we are allowed to place a real fd above 1024.
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if hard != resource.RLIM_INFINITY and hard <= _HIGH_FD:
        pytest.skip(f"fd hard limit {hard} too low to place an fd at {_HIGH_FD}")
    target_soft = _HIGH_FD + 50 if hard == resource.RLIM_INFINITY else min(hard, _HIGH_FD + 50)
    resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))

    primary, secondary = pty.openpty()
    high_primary = -1
    try:
        # Relocate the pty primary onto a high fd number to reproduce the bug.
        os.dup2(primary, _HIGH_FD)
        high_primary = _HIGH_FD
        os.close(primary)
        primary = -1
        assert high_primary >= 1024

        with ConcurrencyGroup(name="terminal-high-fd-test") as group:
            manager = LocalTerminalManager(
                environment_id="env-high-fd",
                terminal_index=0,
                workspace_path=tmp_path,
                working_directory=tmp_path,
                concurrency_group=group,
            )
            # Inject the high-fd pty directly; we are exercising _read_loop, not start().
            manager._pty_process = _HighFdPtyProcess(high_primary)

            received = bytearray()
            received_lock = threading.Lock()

            def _collect(data: bytes) -> None:
                with received_lock:
                    received.extend(data)

            manager.subscribe(_collect)

            reader = threading.Thread(target=manager._read_loop, name="test-pty-reader", daemon=True)
            reader.start()
            try:
                os.write(secondary, b"hello-high-fd\n")
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    with received_lock:
                        if b"hello-high-fd" in bytes(received):
                            break
                    time.sleep(0.02)
            finally:
                manager._stop_reader.set()
                reader.join(timeout=2.0)

            with received_lock:
                got = bytes(received)
        # Assert outside the ConcurrencyGroup context so a failure surfaces as a
        # plain AssertionError rather than being re-wrapped by the group's __exit__.
        assert b"hello-high-fd" in got, (
            f"pty reader produced no output for high-numbered fd {high_primary}; select(2) fails for fds >= 1024"
        )
    finally:
        for fd in (primary, high_primary, secondary):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
