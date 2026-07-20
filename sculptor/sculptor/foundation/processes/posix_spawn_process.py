"""A ``subprocess.Popen``-compatible local process backed by ``os.posix_spawn``.

The backend spawns short-lived helpers (git especially) through
``subprocess.Popen``, which uses ``fork()`` + ``exec()``. ``fork()`` copies the
parent's page tables, so on a long-lived backend whose RSS has grown to many GB
the spawn cost scales with memory — each ``git`` call gets slower the longer the
session runs (SCU-1624). ``os.posix_spawn`` uses ``vfork`` semantics and does not
copy page tables, decoupling spawn cost from RSS. Terminals already moved to
``posix_spawn`` for the same reason (see ``spawned_pty_process.py``).

This is a *minimal* Popen stand-in: it implements only the surface the backend's
process machinery (``ConcurrencyGroup`` → ``RunningProcess`` →
``run_local_command_modern_version``) actually touches — ``pid``/``returncode``,
the three pipe streams, ``poll``/``wait`` (``wait`` raises
``subprocess.TimeoutExpired`` exactly like Popen so the existing shutdown path is
unchanged), and ``terminate``/``kill``/``send_signal``. So those layers can rely
on this instead of ``subprocess`` without other changes.

``cwd`` is intentionally NOT supported: ``POSIX_SPAWN_CHDIR`` is unavailable on
macOS, so there is no fork-free way to set the child's directory here. Callers
that need a working directory pass it another way — git uses ``git -C <dir>`` —
and the spawn machinery only routes ``cwd is None`` commands through here.
"""

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from collections.abc import Sequence
from typing import IO
from typing import Protocol
from typing import runtime_checkable

# Granularity of the busy-wait inside ``wait(timeout=...)``. Small enough that
# shutdown latency is dominated by the child's own SIGTERM handling, not by us.
_WAIT_POLL_INTERVAL_SECONDS = 0.005


# Returncode recorded when the child was reaped out from under us (``waitpid``
# raised ECHILD), so its true exit status is unrecoverable. We surface a distinct
# non-``None`` sentinel rather than leaving ``returncode`` at ``None``: callers
# poll ``returncode``/``poll()`` to detect exit, so a lingering ``None`` would make
# ``poll()`` look "still running" forever (and a default ``timeout=None`` ``wait()``
# would never return). The value mirrors the ``-9999`` style of
# ``SUBPROCESS_STOPPED_BY_REQUEST_EXIT_CODE`` so it stands out in logs.
EXIT_CODE_REAPED_ELSEWHERE = -9998


@runtime_checkable
class LocalProcessHandle(Protocol):
    """The subset of ``subprocess.Popen`` the backend spawn machinery relies on.

    Both ``subprocess.Popen`` and ``PosixSpawnedProcess`` satisfy this, so the
    spawn/termination/output code can accept either.
    """

    pid: int
    returncode: int | None
    stdin: IO[bytes] | None
    stdout: IO[bytes] | None
    stderr: IO[bytes] | None

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


class PosixSpawnedProcess:
    """A ``os.posix_spawn``-backed process exposing the ``LocalProcessHandle`` surface.

    NOT thread-safe. Unlike ``subprocess.Popen`` (which serializes reaping with an
    internal ``_waitpid_lock``), this class has no locking: concurrent ``poll``/
    ``wait`` from two threads can both ``waitpid`` the same pid (one then sees
    ECHILD), and a ``terminate``/``kill`` racing a reap can signal a recycled pid.
    This is safe as used today — the git spawn path drives ``poll``/``wait`` from a
    single worker thread and never hands the handle to another thread (e.g.
    ``RunningProcess.kill_now``). Add locking here before routing any
    ``kill_now``-exposed or otherwise multi-threaded caller through posix_spawn.
    """

    def __init__(
        self,
        *,
        args: Sequence[str],
        pid: int,
        stdin: IO[bytes] | None,
        stdout: IO[bytes] | None,
        stderr: IO[bytes] | None,
    ) -> None:
        self.args = list(args)
        self.pid = pid
        self.returncode: int | None = None
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        # Once we have reaped the child via waitpid, a second waitpid would raise
        # ECHILD; guard so poll()/wait() are idempotent after exit.
        self._reaped = False

    def _record_exit(self, status: int) -> int:
        # Matches subprocess.Popen.returncode semantics: negative for signal N.
        self.returncode = os.waitstatus_to_exitcode(status)
        self._reaped = True
        return self.returncode

    def _record_reaped_elsewhere(self) -> int:
        # waitpid raised ECHILD: something else reaped the child (or there was no
        # such child), so we can never learn its real status. Record the sentinel
        # once so poll()/wait() stay idempotent and always return a non-None code.
        if self.returncode is None:
            self.returncode = EXIT_CODE_REAPED_ELSEWHERE
        self._reaped = True
        return self.returncode

    def poll(self) -> int | None:
        if self._reaped:
            return self.returncode
        try:
            reaped_pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return self._record_reaped_elsewhere()
        if reaped_pid == 0:
            return None
        return self._record_exit(status)

    def wait(self, timeout: float | None = None) -> int:
        if self._reaped:
            assert self.returncode is not None
            return self.returncode
        if timeout is None:
            try:
                _reaped_pid, status = os.waitpid(self.pid, 0)
            except ChildProcessError:
                return self._record_reaped_elsewhere()
            return self._record_exit(status)
        deadline = time.monotonic() + timeout
        while True:
            exit_code = self.poll()
            if exit_code is not None:
                return exit_code
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(_WAIT_POLL_INTERVAL_SECONDS)

    def send_signal(self, sig: signal.Signals) -> None:
        if self._reaped:
            return
        try:
            os.kill(self.pid, sig)
        except ProcessLookupError:
            pass

    def terminate(self) -> None:
        self.send_signal(signal.SIGTERM)

    def kill(self) -> None:
        self.send_signal(signal.SIGKILL)


def _close_quietly(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def spawn_via_posix_spawn(
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    stdin_mode: int = subprocess.DEVNULL,
) -> PosixSpawnedProcess:
    """Spawn ``command`` via ``os.posix_spawn`` with stdout/stderr pipes.

    Mirrors the relevant ``subprocess.Popen`` behavior of
    ``run_local_command_modern_version``: stdout/stderr captured via pipes and
    stdin from ``/dev/null`` (or a pipe when ``stdin_mode`` is ``subprocess.PIPE``).

    Process-group isolation (``start_new_session``/``setsid``) is intentionally NOT
    supported here: nothing that opts into this fast path needs it (git does not),
    and ``posix_spawn``'s ``setsid`` is unavailable on some libc builds. The spawn
    machinery only routes non-isolated commands through here and uses
    ``subprocess.Popen`` (whose ``start_new_session=True`` is portable) otherwise.

    The executable is resolved to an absolute path (``posix_spawn`` does not search
    ``PATH``). Raises ``OSError`` if the command cannot be spawned — the caller maps
    that to ``ProcessSetupError`` just as it does for Popen.
    """
    argv = list(command)
    if not argv:
        # Raise ValueError (not IndexError) so the caller's (OSError, ValueError)
        # handler maps it to ProcessSetupError, matching how subprocess.Popen([]) fails.
        raise ValueError("command must be a non-empty sequence")
    spawn_env = dict(env) if env is not None else dict(os.environ)
    executable = argv[0]
    if not os.path.isabs(executable):
        # Resolve against the child's PATH, not the parent's, so a caller-provided
        # PATH picks the same binary posix_spawn will exec — matching
        # subprocess.Popen(env=...). (posix_spawn itself never searches PATH.)
        resolved = shutil.which(executable, path=spawn_env.get("PATH"))
        if resolved is None:
            raise FileNotFoundError(f"command not found on PATH: {executable!r}")
        executable = resolved

    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    stdin_read = -1
    stdin_write = -1
    devnull_fd = -1
    # ``os.pipe`` fds are close-on-exec, so the ends we don't dup2 into the child
    # are closed automatically at exec; the dup2 targets (0/1/2) are kept. We open
    # /dev/null with O_CLOEXEC for the same reason.
    file_actions: list[tuple[int, ...]] = []
    try:
        if stdin_mode == subprocess.PIPE:
            stdin_read, stdin_write = os.pipe()
            file_actions.append((os.POSIX_SPAWN_DUP2, stdin_read, 0))
        else:
            devnull_fd = os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC)
            file_actions.append((os.POSIX_SPAWN_DUP2, devnull_fd, 0))
        file_actions.append((os.POSIX_SPAWN_DUP2, stdout_write, 1))
        file_actions.append((os.POSIX_SPAWN_DUP2, stderr_write, 2))

        pid = os.posix_spawn(
            executable,
            argv,
            spawn_env,
            file_actions=file_actions,
        )
    except BaseException:
        for fd in (stdout_read, stdout_write, stderr_read, stderr_write, stdin_read, stdin_write, devnull_fd):
            if fd >= 0:
                _close_quietly(fd)
        raise

    # Parent keeps the read ends (stdout/stderr) and the stdin write end; the
    # opposite ends belong to the child.
    _close_quietly(stdout_write)
    _close_quietly(stderr_write)
    if stdin_read >= 0:
        _close_quietly(stdin_read)
    if devnull_fd >= 0:
        _close_quietly(devnull_fd)

    stdin_file = os.fdopen(stdin_write, "wb", buffering=0) if stdin_write >= 0 else None
    stdout_file = os.fdopen(stdout_read, "rb", buffering=0)
    stderr_file = os.fdopen(stderr_read, "rb", buffering=0)
    return PosixSpawnedProcess(args=argv, pid=pid, stdin=stdin_file, stdout=stdout_file, stderr=stderr_file)
