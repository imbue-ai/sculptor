"""Single-use helper subprocess that spawns a pty-backed shell.

Invoked once per terminal via ``os.posix_spawn`` from the
multi-threaded Sculptor backend.  ``posix_spawn`` does not run
Python atfork handlers in the parent (it uses ``posix_spawnp`` /
``vfork`` semantics under the hood), so launching this helper from
the multi-threaded backend is safe with respect to the
fork-in-MT-process lock-leakage deadlock that plagues a direct
``os.fork()`` call.

This module is single-threaded by construction: a fresh Python
interpreter, stdlib-only imports at module top level, no
thread-spawning side effects.  Inside the helper, ``pty.fork()``
(libc ``forkpty(3)``: openpty + fork + setsid +
controlling-terminal setup + dup2) runs while only one thread
exists, so it cannot inherit a lock held by another thread.

The helper exits immediately after the SCM_RIGHTS handoff.  The
shell it forked becomes orphaned and is reparented to init / launchd,
which reaps the eventual zombie.  The backend detects shell death by
polling ``os.kill(shell_pid, 0)`` for ``ProcessLookupError``; it
does not learn the shell's exit code, which no consumer of
``SpawnedPtyProcess`` reads.  Keeping the helper alive to ``waitpid``
the shell and forward the exit code would cost ~10-20 MB unique RSS
per open terminal — unacceptable at the scale a power user opens
terminals.

Wire protocol over the socketpair inherited via the
``_SCULPTOR_PTY_HELPER_FD`` env var:

    parent -> helper:
        config message (multiprocessing.Connection.send):
            {"shell": str, "argv": [str], "cwd": str,
             "env": {str: str}, "rows": int, "cols": int}

    helper -> parent, in order:
        ("ok", shell_pid)                               -- spawn ok
        <SCM_RIGHTS handle: primary pty fd>             -- via send_handle
        (helper exits)

    or, on failure at any stage:
        ("error", stage, summary, traceback)
        (helper exits 1)

The status-first ordering means that a helper crash inside
``pty.fork()`` or post-fork setup surfaces with a real traceback
instead of an opaque EOF on the parent's ``recv_handle`` call.
"""

import fcntl
import os
import pty
import signal
import struct
import sys
import termios
import traceback
from multiprocessing.connection import Connection
from multiprocessing.reduction import send_handle
from typing import Final
from typing import NoReturn

HELPER_FD_ENV: Final[str] = "_SCULPTOR_PTY_HELPER_FD"

_EXIT_EXEC_NOT_FOUND: Final[int] = 127
_EXIT_EXEC_FAILED: Final[int] = 126
_EXIT_HELPER_BAD_ARGS: Final[int] = 2

_CATCHABLE_SIGNALS: Final[tuple[int, ...]] = (
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGHUP,
    signal.SIGPIPE,
)


def _report_error_and_exit(conn: Connection | None, stage: str, exc: BaseException) -> NoReturn:
    """Send a typed ``("error", ...)`` message to the parent and exit.

    Best-effort: if the parent has already closed the socket or the
    connection is otherwise unusable, fall through to ``sys.exit(1)`` so
    the parent at least observes EOF.
    """
    tb = traceback.format_exc()
    summary = f"{stage}: {type(exc).__name__}: {exc!s}"
    if conn is not None:
        try:
            conn.send(("error", stage, summary, tb))
        except (BrokenPipeError, OSError, EOFError):
            pass
        try:
            conn.close()
        except OSError:
            pass
    sys.exit(1)


def _open_parent_connection() -> Connection:
    fd_value = os.environ.get(HELPER_FD_ENV)
    if fd_value is None:
        sys.stderr.write(f"pty_helper: {HELPER_FD_ENV} is not set\n")
        sys.exit(_EXIT_HELPER_BAD_ARGS)
    # Default satisfies the type checker's flow analysis: the except branch
    # calls ``sys.exit`` (``NoReturn``) but that is not propagated here.
    fd: int = -1
    try:
        fd = int(fd_value)
    except ValueError:
        sys.stderr.write(f"pty_helper: invalid {HELPER_FD_ENV}: {fd_value!r}\n")
        sys.exit(_EXIT_HELPER_BAD_ARGS)
    return Connection(fd)


def _exec_shell_in_grandchild(shell: str, argv: list[str], cwd: str, env: dict[str, str]) -> NoReturn:
    """Final stage of the grandchild: chdir, reset signals, execvpe.

    Runs in the pty grandchild between ``pty.fork()`` returning 0 and
    the user's shell taking over the address space.  The grandchild is
    single-threaded by construction (forked from the single-threaded
    helper) so no atfork hazards exist.
    """
    for sig in _CATCHABLE_SIGNALS:
        try:
            signal.signal(sig, signal.SIG_DFL)
        except (OSError, ValueError):
            pass
    try:
        os.chdir(cwd)
    except FileNotFoundError:
        os._exit(_EXIT_EXEC_FAILED)
    except OSError:
        os._exit(_EXIT_EXEC_FAILED)
    try:
        os.execvpe(shell, argv, env)
    except FileNotFoundError:
        os._exit(_EXIT_EXEC_NOT_FOUND)
    except OSError:
        os._exit(_EXIT_EXEC_FAILED)
    # execvpe doesn't return on success; if we get here something is wrong.
    os._exit(1)


def _send_initial_status_and_fd(conn: Connection, primary_fd: int, shell_pid: int, rows: int, cols: int) -> None:
    """Configure ``primary_fd`` and ship it (with the shell pid) to the parent.

    On any failure, kill the shell so we don't leak a runaway child, then
    re-raise so the caller's outer handler reports the error.
    """
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(primary_fd, termios.TIOCSWINSZ, winsize)
        flags = fcntl.fcntl(primary_fd, fcntl.F_GETFL)
        fcntl.fcntl(primary_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        # Send the "ok" tuple before the SCM_RIGHTS handle so a crash here
        # surfaces as a typed error tuple instead of an EOF during recv_handle.
        conn.send(("ok", shell_pid))
        send_handle(conn, primary_fd, None)
    except BaseException:
        try:
            os.kill(shell_pid, signal.SIGKILL)
        except OSError:
            pass
        raise


def main() -> None:
    # Defensive defaults satisfy the type checker's flow analysis: the except
    # branches below all call ``_report_error_and_exit`` (``NoReturn``), but
    # that is not propagated into the surrounding scope, so the variables must
    # be definitely-assigned along every path.
    config: object = None
    shell: str = ""
    argv: list[str] = []
    cwd: str = ""
    env_dict: dict[str, str] = {}
    rows: int = 0
    cols: int = 0
    shell_pid: int = -1
    primary_fd: int = -1

    conn = _open_parent_connection()
    try:
        config = conn.recv()
    except (EOFError, OSError) as exc:
        _report_error_and_exit(conn, "recv config", exc)

    if not isinstance(config, dict):
        _report_error_and_exit(
            conn, "validate config", TypeError(f"expected dict config, got {type(config).__name__}")
        )

    try:
        shell = str(config["shell"])
        argv = [str(a) for a in config["argv"]]
        cwd = str(config["cwd"])
        env_dict = {str(k): str(v) for k, v in config["env"].items()}
        rows = int(config["rows"])
        cols = int(config["cols"])
    except (KeyError, TypeError, ValueError) as exc:
        _report_error_and_exit(conn, "parse config", exc)

    try:
        shell_pid, primary_fd = pty.fork()
    except BaseException as exc:
        _report_error_and_exit(conn, "pty.fork", exc)

    if shell_pid == 0:
        _exec_shell_in_grandchild(shell, argv, cwd, env_dict)

    try:
        _send_initial_status_and_fd(conn, primary_fd, shell_pid, rows, cols)
    except BaseException as exc:
        _report_error_and_exit(conn, "post-fork setup", exc)

    # Close our copy so the kernel delivers SIGHUP to the shell when the
    # backend later closes its SCM_RIGHTS-dup'd copy of the primary fd.
    os.close(primary_fd)

    # Helper exits immediately after the handoff.  The shell becomes init's
    # child and init reaps it.  The backend detects shell death via
    # ``os.kill(shell_pid, 0)`` polling; not learning the exact exit code
    # is the price we pay for not parking ~10-20 MB of unique RSS per open
    # terminal.
    try:
        conn.close()
    except OSError:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
