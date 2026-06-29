"""RunningProcess implementation backed by a short-lived posix_spawn helper.

The Sculptor backend is multi-threaded, so a direct ``os.fork()``
risks a deadlock when another thread holds a Python-internal lock
(loguru's queue lock is the textbook offender): the parent thread's
``PyOS_BeforeFork`` waits for that lock while holding the GIL, and
the lock-holder waits for the GIL.  One unlucky fork is enough to
wedge the interpreter.

``SpawnedPtyProcess`` avoids that hazard without standing up a
long-lived forkserver.  Each terminal open launches a fresh,
single-use helper subprocess via ``os.posix_spawn``, which (under
``posix_spawnp`` / ``vfork`` semantics) does not run Python atfork
handlers in the parent.  The helper itself is a fresh Python
interpreter -- single-threaded by construction -- which means its
``pty.fork()`` call cannot inherit a leaked lock.

The helper exits as soon as it has handed the pty primary fd back
via ``SCM_RIGHTS``.  The forked shell then becomes init's child;
init reaps the eventual zombie.  We detect shell death by polling
``os.kill(shell_pid, 0)`` for ``ProcessLookupError`` rather than by
``waitpid``-ing — keeping the helper parked in ``waitpid`` would
cost ~10-20 MB of unique RSS per open terminal, which is real money
at the scale a power user opens terminals (50+ is plausible).  The
price is that we lose the shell's exit code, but no consumer of
``SpawnedPtyProcess`` reads it (terminal panels treat any EOF on the
primary fd as "shell exited").

Trade-offs vs. a long-lived forkserver:

  - Per-spawn cost is a full Python interpreter cold start
    (~100-200ms).  Acceptable: terminal open is user-initiated and
    not on any hot path.
  - No long-lived helper to crash, hang, restart, or health-check.
  - Each spawn is independent: one helper's failure or hang affects
    one terminal, not the pool.
  - No bootstrap ordering or import discipline to maintain.
  - Constant RSS overhead per open terminal (helper exits after
    handoff).

See ``pty_helper.py`` for the wire protocol.
"""

import os
import signal
import socket
import sys
import time
from multiprocessing.connection import Connection
from multiprocessing.reduction import recv_handle
from pathlib import Path
from queue import Queue
from subprocess import TimeoutExpired
from typing import Any
from typing import Final
from typing import Mapping
from typing import Sequence

from loguru import logger

from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.services.workspace_service.environment_manager.environments.pty_helper import HELPER_FD_ENV
from sculptor.utils.build import is_packaged

DEFAULT_TERMINAL_ROWS: Final[int] = 24
DEFAULT_TERMINAL_COLS: Final[int] = 80
TERMINAL_TYPE: Final[str] = "xterm-256color"

# Sentinel argv used to dispatch the bootstrap (``sculptor.cli.main``)
# into ``pty_helper.main()`` instead of the normal backend startup.
# In a PyInstaller bundle ``sys.executable`` IS the bootstrap binary
# (``sculptor_backend``), so we can't re-invoke it with ``python -m``
# -- the argv-sentinel dispatch is what lets the same binary serve as
# both the backend and its own pty helper.
_PTY_HELPER_FLAG: Final[str] = "--pty-helper"

# Dotted-module path used to invoke the helper in dev (non-frozen)
# mode, where ``sys.executable`` is a real Python interpreter and we
# can take advantage of ``python -m`` to skip importing
# ``sculptor.cli.main`` entirely.  In the bundle this path is unused.
_HELPER_MODULE: Final[str] = "sculptor.services.workspace_service.environment_manager.environments.pty_helper"

# How long the backend waits for the helper to report "ok" + send the pty
# primary fd back. This is the bound on the worst case where the helper
# starts but never responds (kernel pty exhaustion, swap thrashing, etc.).
# In practice the helper responds in well under a second.
_SPAWN_TIMEOUT_SECONDS: Final[float] = 30.0

# How long ``start()`` waits for the helper to exit after the SCM_RIGHTS
# handoff. The helper has no work left at that point -- it closes its
# socket and calls ``sys.exit(0)``. Beyond this budget we leave reaping
# to the OS rather than blocking the caller indefinitely on a stuck
# helper.
_HELPER_EXIT_TIMEOUT_SECONDS: Final[float] = 1.0

# Polling interval used while reaping the just-exited helper.
_HELPER_EXIT_POLL_INTERVAL_SECONDS: Final[float] = 0.005

# Polling interval used by ``wait()`` to check whether the shell is still
# alive via ``os.kill(pid, 0)``.
_SHELL_DEATH_POLL_INTERVAL_SECONDS: Final[float] = 0.05

# Sentinel returncode used when the shell has exited.  We do not have the
# real exit code (the helper exited before ``waitpid`` so init reaped the
# shell instead).  No consumer of ``SpawnedPtyProcess`` reads the exit
# code -- ``terminate()`` only cares that ``poll()`` returns non-None,
# and ``is_checked=False`` keeps the concurrency group from inspecting it.
_SHELL_EXITED_SENTINEL: Final[int] = 0

_EXCLUDED_ENV_VAR_NAMES: Final[frozenset[str]] = frozenset({"SESSION_TOKEN", "TMUX", "TMUX_PANE"})
_EXCLUDED_ENV_VAR_PREFIXES: Final[tuple[str, ...]] = ("SCULPT_", "SCULPTOR_", "_PYI_")


class PtyHelperSpawnError(RuntimeError):
    """Raised when the posix_spawn helper fails to deliver a usable pty."""


def _scrub_shell_env(extra_env: Mapping[str, str], env_var_override: bool) -> dict[str, str]:
    """Build the environment the shell will see, starting from the backend's
    environment and stripping Sculptor's internal vars.

    Done in the backend (rather than in the post-fork window of the helper)
    so the helper's grandchild does as little work as possible between
    ``pty.fork()`` and ``execvpe``.

    ``SCULPT_*`` (no trailing O) is the user-facing CLI's env-var family;
    scrubbing it prevents Sculptor-on-Sculptor sessions from pointing the
    inner ``sculpt`` CLI at the outer backend.  ``_PYI_*`` is the
    PyInstaller bootloader's namespace.

    ``TMUX``/``TMUX_PANE`` are scrubbed because a Sculptor PTY is never a real
    tmux pane. A stale value (e.g. when the dev backend itself runs under tmux)
    makes TUIs such as pi switch to tmux key handling, where a plain carriage
    return no longer registers as Enter. Absent in production (the backend does
    not run under tmux), so this is a no-op there.
    """
    env = dict(os.environ)
    for var in list(env):
        if var in _EXCLUDED_ENV_VAR_NAMES or var.startswith(_EXCLUDED_ENV_VAR_PREFIXES):
            del env[var]
    for key, value in extra_env.items():
        if key == "PATH":
            env["PATH"] = value + os.pathsep + env.get("PATH", "")
        elif env_var_override or key not in env:
            env[key] = value
    env["TERM"] = TERMINAL_TYPE
    return env


def _build_helper_env(child_fd: int) -> dict[str, str]:
    """The helper's own process environment.

    Distinct from the *shell* env: the helper inherits the backend's
    environment plus the socketpair fd number it should read from. The
    shell env is delivered separately over the socket and never leaks
    into the helper interpreter itself.
    """
    env = dict(os.environ)
    env[HELPER_FD_ENV] = str(child_fd)
    return env


def _close_quietly(closeable: socket.socket | Connection | None) -> None:
    if closeable is None:
        return
    try:
        closeable.close()
    except OSError:
        pass


def _kill_and_reap_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except (ChildProcessError, OSError):
        pass


def _build_helper_argv() -> list[str]:
    """Return the argv that launches a single pty helper subprocess.

    In dev mode ``sys.executable`` is a real Python interpreter, so we
    invoke the helper module directly with ``-m``.  This skips loading
    ``sculptor.cli.main`` entirely and is the fastest path.

    In the packaged app ``sys.executable`` is the ``sculptor_backend``
    PyInstaller bootloader, which always runs ``sculptor/cli/main.py``
    as its entry script and cannot accept ``-m``.  We re-invoke it
    with the ``--pty-helper`` sentinel, which the bootstrap dispatches
    into ``pty_helper.main()`` before any heavy backend import runs.
    """
    if is_packaged():
        return [sys.executable, _PTY_HELPER_FLAG]
    return [sys.executable, "-m", _HELPER_MODULE]


def _spawn_helper_subprocess(child_sock: socket.socket) -> int:
    """Launch the helper subprocess and return its pid.

    Uses ``os.posix_spawn`` rather than ``subprocess.Popen`` so the call
    site is exactly the spawn primitive whose safety we care about: it
    does not run Python atfork handlers in the parent.
    """
    os.set_inheritable(child_sock.fileno(), True)
    helper_env = _build_helper_env(child_sock.fileno())
    return os.posix_spawn(
        sys.executable,
        _build_helper_argv(),
        helper_env,
    )


def _send_config(
    conn: Connection,
    shell: str,
    argv: Sequence[str],
    cwd: str,
    shell_env: Mapping[str, str],
    rows: int,
    cols: int,
) -> None:
    # A helper that dies before reading the config can close its socket end
    # before our write completes, surfacing as BrokenPipeError here rather
    # than as EOF in _await_ok_and_fd. Both mean the same thing to callers:
    # the helper failed to start. Translate so the caller sees one error type.
    try:
        conn.send(
            {
                "shell": shell,
                "argv": list(argv),
                "cwd": cwd,
                "env": shell_env,
                "rows": rows,
                "cols": cols,
            }
        )
    except (BrokenPipeError, EOFError) as exc:
        raise PtyHelperSpawnError("pty helper exited before accepting config") from exc
    except OSError as exc:
        raise PtyHelperSpawnError(f"failed to send config to pty helper: {exc!s}") from exc


def _await_ok_and_fd(conn: Connection) -> tuple[int, int]:
    """Wait for the helper's first status message, then receive the pty fd.

    Returns ``(shell_pid, primary_fd)`` on success. Raises
    :class:`PtyHelperSpawnError` on any failure mode (timeout, EOF, typed
    error message, malformed message, or fd-receive failure).
    """
    if not conn.poll(_SPAWN_TIMEOUT_SECONDS):
        raise PtyHelperSpawnError(f"pty helper did not respond within {_SPAWN_TIMEOUT_SECONDS}s")
    try:
        first = conn.recv()
    except EOFError as exc:
        raise PtyHelperSpawnError("pty helper exited without sending status") from exc
    except OSError as exc:
        raise PtyHelperSpawnError(f"failed to read helper status: {exc!s}") from exc

    if not (isinstance(first, tuple) and first):
        raise PtyHelperSpawnError(f"unexpected first message from pty helper: {first!r}")

    if first[0] == "error":
        if len(first) >= 4:
            _, stage, summary, tb = first[:4]
            raise PtyHelperSpawnError(f"pty helper failed at {stage}: {summary}\n--- helper traceback ---\n{tb}")
        raise PtyHelperSpawnError(f"pty helper reported error: {first!r}")

    if first[0] != "ok" or len(first) < 2:
        raise PtyHelperSpawnError(f"unexpected first message from pty helper: {first!r}")

    shell_pid = int(first[1])

    try:
        primary_fd = recv_handle(conn)
    except (EOFError, OSError) as exc:
        raise PtyHelperSpawnError(f"failed to receive primary fd from helper: {exc!s}") from exc
    return shell_pid, primary_fd


class _SpawnedHelper:
    """Backend-side handle for one pty shell.

    The helper subprocess that originally forked the shell has already
    exited by the time this object is constructed (it exits as soon as
    it hands the primary fd back via SCM_RIGHTS).  The shell is now an
    orphan reparented to init; we track it by pid only.
    """

    def __init__(self, shell_pid: int, primary_fd: int) -> None:
        self._shell_pid = shell_pid
        self._primary_fd = primary_fd
        self._returncode: int | None = None

    @property
    def shell_pid(self) -> int:
        return self._shell_pid

    @property
    def primary_fd(self) -> int:
        return self._primary_fd

    def poll(self) -> int | None:
        """Return ``_SHELL_EXITED_SENTINEL`` if the shell has died, else None.

        Uses ``os.kill(pid, 0)`` rather than ``waitpid``: the shell is not
        our child (it was orphaned when the helper exited), so ``waitpid``
        would return ``ECHILD``.  The pid-reuse race is small in practice
        (macOS pids wrap at high numbers, and the shell pid stays in the
        process table until init reaps it) but is a known limitation
        documented in the module docstring.
        """
        if self._returncode is not None:
            return self._returncode
        try:
            os.kill(self._shell_pid, 0)
        except ProcessLookupError:
            self._returncode = _SHELL_EXITED_SENTINEL
            return self._returncode
        except PermissionError:
            # The shell still exists (otherwise we'd get ESRCH); we just
            # can't signal it.  Treat as alive.
            return None
        return None

    def wait(self, timeout: float | None = None) -> int:
        deadline: float | None = None if timeout is None else time.monotonic() + timeout
        while True:
            rc = self.poll()
            if rc is not None:
                return rc
            if deadline is None:
                time.sleep(_SHELL_DEATH_POLL_INTERVAL_SECONDS)
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutExpired(cmd=f"pty-shell-{self._shell_pid}", timeout=timeout or 0.0)
            time.sleep(min(remaining, _SHELL_DEATH_POLL_INTERVAL_SECONDS))


def _reap_just_exited_helper(helper_pid: int) -> None:
    """Reap the helper subprocess, which should have just exited.

    Called immediately after the SCM_RIGHTS handoff: the helper has no
    remaining work and is about to close its socket and ``sys.exit(0)``.
    We poll ``waitpid`` for a brief bounded window rather than blocking
    indefinitely on a stuck helper.
    """
    deadline = time.monotonic() + _HELPER_EXIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            pid, _ = os.waitpid(helper_pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid != 0:
            return
        time.sleep(_HELPER_EXIT_POLL_INTERVAL_SECONDS)
    logger.warning(
        "pty helper pid={} did not exit within {:.1f}s after SCM_RIGHTS handoff; leaving to OS reaper",
        helper_pid,
        _HELPER_EXIT_TIMEOUT_SECONDS,
    )


def _spawn_helper(
    shell: str,
    argv: Sequence[str],
    cwd: str,
    shell_env: Mapping[str, str],
    rows: int,
    cols: int,
) -> _SpawnedHelper:
    """Spawn a fresh helper subprocess, receive the pty fd, reap the helper.

    The helper is single-use: it forks the shell, ships the primary fd
    back via SCM_RIGHTS, then exits.  By the time this function returns,
    the helper has been reaped; only the (now-orphaned) shell remains.

    All failure paths close the socketpair and (if the helper made it as
    far as posix_spawn) kill + reap the helper so we don't leak a
    runaway interpreter.
    """
    parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    helper_pid: int | None = None
    conn: Connection | None = None
    try:
        helper_pid = _spawn_helper_subprocess(child_sock)
        # Once posix_spawn returns, the helper holds its own copy of the
        # socketpair end; we drop the parent's reference so we are not
        # waiting on our own write end at recv() time.
        _close_quietly(child_sock)
        conn = Connection(parent_sock.detach())

        _send_config(conn, shell, argv, cwd, shell_env, rows, cols)
        shell_pid, primary_fd = _await_ok_and_fd(conn)
    except BaseException:
        _close_quietly(conn)
        _close_quietly(parent_sock)
        _close_quietly(child_sock)
        if helper_pid is not None:
            _kill_and_reap_quietly(helper_pid)
        raise

    # Handoff done.  Close our end of the socket (the helper closed its
    # end already and is exiting), then reap the helper.
    _close_quietly(conn)
    logger.debug("Spawned pty helper pid={} for shell pid={}", helper_pid, shell_pid)
    _reap_just_exited_helper(helper_pid)
    return _SpawnedHelper(shell_pid=shell_pid, primary_fd=primary_fd)


class SpawnedPtyProcess(RunningProcess):
    """A pty-backed shell process spawned via a posix_spawn helper.

    Standard ``RunningProcess`` surface (primary fd for I/O,
    ``terminate()`` with SIGTERM-then-SIGKILL, ``close_primary_fd`` to
    deliver SIGHUP to the shell), but the actual ``pty.fork()`` happens
    inside a fresh single-threaded helper interpreter so the
    multi-threaded backend never calls fork directly.
    """

    def __init__(
        self,
        name: str,
        working_directory: Path,
        shell: str | None = None,
        extra_env: Mapping[str, str] | None = None,
        env_var_override: bool = False,
    ) -> None:
        self._name = name
        self._working_directory = working_directory
        self._shell = shell or os.environ.get("SHELL", "/bin/bash")
        self._extra_env = extra_env or {}
        self._env_var_override = env_var_override

        self._helper: _SpawnedHelper | None = None
        self._returncode: int | None = None
        self._is_primary_fd_closed = False

    @property
    def primary_fd(self) -> int | None:
        if self._helper is None or self._is_primary_fd_closed:
            return None
        return self._helper.primary_fd

    @property
    def shell_pid(self) -> int | None:
        return self._helper.shell_pid if self._helper is not None else None

    @property
    def is_checked(self) -> bool:
        return False

    @property
    def returncode(self) -> int | None:
        return self.poll()

    @property
    def command(self) -> tuple[str, ...]:
        return (self._name,)

    def start(self, kwargs: Mapping[str, Any] | None = None) -> None:
        if self._helper is not None:
            raise RuntimeError("Process already started")
        shell_env = _scrub_shell_env(self._extra_env, self._env_var_override)
        self._helper = _spawn_helper(
            shell=self._shell,
            argv=[self._shell, "-l"],
            cwd=str(self._working_directory),
            shell_env=shell_env,
            rows=DEFAULT_TERMINAL_ROWS,
            cols=DEFAULT_TERMINAL_COLS,
        )

    def poll(self) -> int | None:
        if self._returncode is not None:
            return self._returncode
        if self._helper is None:
            return None
        rc = self._helper.poll()
        if rc is None:
            return None
        self._returncode = rc
        return rc

    def is_finished(self) -> bool:
        return self.poll() is not None

    def wait(self, timeout: float | None = None) -> int:
        if self._returncode is not None:
            return self._returncode
        if self._helper is None:
            return 0
        rc = self._helper.wait(timeout=timeout)
        self._returncode = rc
        return rc

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        helper = self._helper
        if helper is None or self.is_finished():
            return
        # POSIX interactive login shells (bash -l, zsh) install SIG_IGN for
        # SIGTERM so broad-scope kills don't yank a user's session. We still
        # send it as a cooperative shutdown signal for non-shell PTY
        # children, and as a belt-and-suspenders before SIGKILL.
        try:
            os.kill(helper.shell_pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.wait(timeout=force_kill_seconds)
            return
        except TimeoutExpired:
            pass
        logger.warning(
            "PTY pid={} did not exit within {:.2f}s of SIGTERM (or SIGHUP from primary-fd close); sending SIGKILL",
            helper.shell_pid,
            force_kill_seconds,
        )
        try:
            os.kill(helper.shell_pid, signal.SIGKILL)
            self.wait(timeout=1.0)
        except (ProcessLookupError, TimeoutExpired):
            pass

    def close_primary_fd(self) -> None:
        if self._helper is None or self._is_primary_fd_closed:
            return
        try:
            os.close(self._helper.primary_fd)
        except OSError:
            pass
        self._is_primary_fd_closed = True

    def check(self) -> None:
        pass

    def read_stdout(self) -> str:
        return ""

    def read_stderr(self) -> str:
        return ""

    def get_timed_out(self) -> bool:
        return False

    def run(self, kwargs: Mapping[str, Any]) -> None:
        pass

    def get_queue(self) -> Queue[tuple[str, bool]]:
        raise NotImplementedError("SpawnedPtyProcess does not support output queues")
