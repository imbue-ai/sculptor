"""Local terminal manager for Sculptor environments.

This module implements terminal management using direct pty control for local environments.
Unlike ttyd-based approaches, this keeps the pty alive across WebSocket disconnections,
providing VS Code-like terminal persistence.
"""

import dataclasses
import errno
import fcntl
import hashlib
import os
import select
import struct
import termios
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.interfaces.terminal_manager import TerminalManager
from sculptor.services.workspace_service.environment_manager.env_file_parser import load_project_env_vars
from sculptor.services.workspace_service.environment_manager.environments.spawned_pty_process import SpawnedPtyProcess

# Buffer size for reading from pty — larger buffers reduce syscall overhead
# for bulk output (e.g., `cat large_file`), matching ttyd's approach.
PTY_READ_BUFFER_SIZE = 32768

# Maximum output buffer size (for replay on reconnect) - ~1MB
MAX_OUTPUT_BUFFER_SIZE = 1024 * 1024


@dataclasses.dataclass(frozen=True)
class TerminalEnvironmentConfig:
    """Environment-level configuration needed to create terminals.

    Stored separately from terminal managers so that new terminals can be created
    even if the initial terminal failed to start.

    Project env vars (``~/.sculptor/.env`` and ``.sculptor/.env``) are NOT cached
    here — they are re-read at terminal creation time so that newly opened
    terminals see the latest values on disk. ``extra_env`` holds only the static
    SCULPT_* vars that the agent service injects.
    """

    workspace_path: Path
    working_directory: Path
    concurrency_group: ConcurrencyGroup
    extra_env: dict[str, str] = dataclasses.field(default_factory=dict)
    env_var_override: bool = False
    sculptor_folder: Path | None = None


# Registry of active terminal managers, keyed by terminal_id (URL-safe hash)
_terminal_managers: dict[str, "LocalTerminalManager"] = {}
# Registry of environment configs, keyed by environment_id
_environment_configs: dict[str, TerminalEnvironmentConfig] = {}
_registry_lock = threading.Lock()


def make_terminal_id(environment_id: str, terminal_index: int) -> str:
    """Create a URL-safe terminal ID from an environment ID and terminal index."""
    key = f"{environment_id}:{terminal_index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get_terminal_manager(terminal_id: str) -> "LocalTerminalManager | None":
    """Get a terminal manager by terminal ID."""
    with _registry_lock:
        return _terminal_managers.get(terminal_id)


def register_terminal_manager(terminal_id: str, manager: "LocalTerminalManager") -> "LocalTerminalManager":
    """Atomically register a terminal manager, returning the existing one if already present.

    This prevents race conditions where two threads create duplicate terminals for the
    same environment. The first one to register wins; the second gets back the first.

    Returns:
        The terminal manager that should be used (either the existing one or the newly registered one).
    """
    with _registry_lock:
        existing = _terminal_managers.get(terminal_id)
        if existing is not None:
            return existing
        _terminal_managers[terminal_id] = manager
        return manager


def unregister_terminal_manager(terminal_id: str) -> "LocalTerminalManager | None":
    """Atomically remove a terminal manager from the registry and return it.

    Callers are responsible for calling ``.stop()`` on the returned manager
    (if non-None). Used by the close-terminal HTTP route so an explicit user
    action -- closing the terminal panel -- destroys the shell, instead of
    just disconnecting the WebSocket and leaving the pty + child process
    running until workspace teardown.
    """
    with _registry_lock:
        return _terminal_managers.pop(terminal_id, None)


def register_environment_config(environment_id: str, config: TerminalEnvironmentConfig) -> None:
    """Register environment-level config for terminal creation.

    This is called early during workspace startup so that terminals can be created
    on demand even if the initial eager terminal creation fails.
    """
    with _registry_lock:
        _environment_configs[environment_id] = config


def get_environment_config(environment_id: str) -> TerminalEnvironmentConfig | None:
    """Get the environment config for terminal creation."""
    with _registry_lock:
        return _environment_configs.get(environment_id)


def stop_all_terminals() -> None:
    """Stop and remove all active terminal managers from the global registry.

    Called during workspace service shutdown to ensure terminals are cleanly
    terminated before the ConcurrencyGroup that owns them is shut down.
    Stops all terminals concurrently to avoid slow sequential shutdown.
    """
    with _registry_lock:
        managers = list(_terminal_managers.values())
        _environment_configs.clear()
    _stop_managers_concurrently(managers)


def _stop_one_manager(manager: "LocalTerminalManager") -> None:
    """Stop a single terminal manager, logging any errors."""
    try:
        manager.stop()
    except Exception as e:
        logger.error("Failed to stop terminal manager: {}", e)


def _stop_managers_concurrently(managers: list["LocalTerminalManager"]) -> None:
    """Stop a list of terminal managers concurrently using threads."""
    if not managers:
        return

    threads = [threading.Thread(target=_stop_one_manager, args=(m,), daemon=True) for m in managers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)


def stop_terminals_for_environment(environment_id: str) -> None:
    """Stop all terminal managers (all indices) for a given environment.

    Used during workspace teardown to clean up every terminal index, not just
    the default one. Also removes the environment config so no new terminals
    can be created for this environment.
    """
    with _registry_lock:
        to_stop = [mgr for mgr in _terminal_managers.values() if mgr._environment_id == environment_id]
        _environment_configs.pop(environment_id, None)
    _stop_managers_concurrently(to_stop)


def create_terminal_for_environment(
    environment_id: str,
    terminal_index: int,
) -> "LocalTerminalManager | None":
    """Create a new terminal for the given environment and index.

    Reads configuration from the environment config registry (not from the index-0
    terminal). Returns None if no config is registered or if the terminal fails
    to start.

    The manager is only registered after start() succeeds, so callers can assume
    any manager in the registry has a live pty.
    """
    config = get_environment_config(environment_id)
    if config is None:
        return None

    terminal_id = make_terminal_id(environment_id, terminal_index)

    # Check if already registered (race condition guard).
    existing = get_terminal_manager(terminal_id)
    if existing is not None:
        return existing

    # Re-read project env vars from disk so newly opened terminals see changes
    # the user made to ~/.sculptor/.env or .sculptor/.env after the workspace
    # was created. Sculpt vars (in config.extra_env) layer on top.
    project_env = load_project_env_vars(config.working_directory, sculptor_folder=config.sculptor_folder)
    terminal_extra_env = {**project_env, **config.extra_env}

    manager = LocalTerminalManager(
        environment_id=environment_id,
        terminal_index=terminal_index,
        workspace_path=config.workspace_path,
        working_directory=config.working_directory,
        concurrency_group=config.concurrency_group,
        extra_env=terminal_extra_env,
        env_var_override=config.env_var_override,
    )

    try:
        manager.start()
    except Exception as e:
        # Recoverable: the caller returns None and the connection is retried.
        # DEBUG keeps the exception available for diagnosing persistent
        # failures without alerting on the transient case.
        logger.debug(
            "Failed to start terminal {} for environment {}: {}",
            terminal_index,
            environment_id,
            e,
        )
        return None

    winner = register_terminal_manager(terminal_id, manager)
    if winner is not manager:
        # Another thread won the race — stop our duplicate.
        manager.stop()
    return winner


class LocalTerminalManager(TerminalManager):
    """Terminal manager for local environments using direct pty control.

    This implementation creates a pty directly and manages the shell process.
    The pty stays alive across WebSocket disconnections, providing persistent
    terminal sessions like VS Code.
    """

    def __init__(
        self,
        environment_id: str,
        *,
        terminal_index: int = 0,
        workspace_path: Path,
        working_directory: Path,
        concurrency_group: ConcurrencyGroup,
        extra_env: dict[str, str] | None = None,
        env_var_override: bool = False,
        terminal_id: str | None = None,
    ) -> None:
        """Initialize the local terminal manager.

        Args:
            environment_id: The environment ID for this terminal.
            terminal_index: The index of this terminal within the environment.
            workspace_path: Path to the task's workspace directory.
            working_directory: Path to the terminal's working directory.
            concurrency_group: Long-lived concurrency group for terminal thread/process
                lifecycle management. Should outlive individual agent runs.
            extra_env: Additional environment variables to inject into the shell.
            env_var_override: When True, extra_env values override existing os.environ values.
            terminal_id: Explicit registry id; defaults to the hash of
                (environment_id, terminal_index). Agent-scoped terminals pass
                their own id while keeping environment_id pointing at the
                workspace environment so ``stop_terminals_for_environment``
                still stops them at teardown.
        """
        self._environment_id = environment_id
        self._terminal_id = (
            terminal_id if terminal_id is not None else make_terminal_id(environment_id, terminal_index)
        )
        self._working_directory = working_directory
        self._concurrency_group = concurrency_group
        self._extra_env = extra_env or {}
        self._env_var_override = env_var_override

        # Pty process - handles pty creation and shell execution via a
        # short-lived posix_spawn helper, so the fork(2) the shell needs
        # never runs in this multi-threaded backend process.
        self._pty_process: SpawnedPtyProcess | None = None

        # Output buffer for replay on reconnect, and callbacks notified on new
        # output.  Both are protected by a single lock so that a subscriber can
        # atomically snapshot the buffer and register its callback — otherwise
        # any output produced between "read buffer" and "register callback" is
        # buffered but never delivered to that subscriber.
        self._output_buffer: deque[bytes] = deque()
        self._output_buffer_size = 0
        self._output_callbacks: list[Callable[[bytes], None]] = []
        self._state_lock = threading.Lock()

        # Reader thread
        self._reader_thread: ObservableThread | None = None
        self._stop_reader = threading.Event()

    def start(self) -> None:
        """Start the terminal session.

        Raises:
            RuntimeError: If the terminal fails to start.
        """
        if self._pty_process is not None:
            logger.debug("Terminal already started for environment {}", self._environment_id)
            return

        logger.debug(
            "Starting pty terminal in directory {} for environment {}",
            self._working_directory,
            self._environment_id,
        )

        # Create and start the pty process.
        pty_process = SpawnedPtyProcess(
            name=f"pty-shell-{self._environment_id}",
            working_directory=self._working_directory,
            extra_env=self._extra_env,
            env_var_override=self._env_var_override,
        )
        pty_process.start()
        self._pty_process = pty_process

        # Register the process with the concurrency group for lifecycle management.
        self._concurrency_group.start_background_process_from_factory(lambda: pty_process)

        # Start the reader thread to continuously read output from the pty.
        self._stop_reader.clear()
        self._reader_thread = self._concurrency_group.start_new_thread(
            target=self._read_loop,
            name=f"pty-reader-{self._environment_id}",
            daemon=True,
            # The reader thread exits gracefully when _stop_reader is set or pty closes,
            # so we don't need to check it for errors.
            is_checked=False,
        )

        logger.info(
            "Terminal started for environment {} (terminal_id={})",
            self._environment_id,
            self._terminal_id,
        )

    def _emit_output(self, data: bytes) -> None:
        """Buffer output data and notify connected WebSocket clients.

        Buffer append and callback notification run under the same lock so a
        concurrent `subscribe()` either sees `data` in its snapshot or receives
        it via callback — never neither.  Callbacks are expected to be
        non-blocking (the WS handler hands off to an asyncio queue).
        """
        with self._state_lock:
            self._output_buffer.append(data)
            self._output_buffer_size += len(data)

            while self._output_buffer_size > MAX_OUTPUT_BUFFER_SIZE and self._output_buffer:
                removed = self._output_buffer.popleft()
                self._output_buffer_size -= len(removed)

            callbacks = list(self._output_callbacks)

            for callback in callbacks:
                try:
                    callback(data)
                except Exception as e:
                    logger.error("Output callback error: {}", e)

    def _read_loop(self) -> None:
        """Background thread that reads from the pty and buffers output."""
        if self._pty_process is None:
            return
        primary_fd = self._pty_process.primary_fd
        if primary_fd is None:
            return

        # Wait for pty output with poll(2) rather than select(2): select cannot
        # wait on a file descriptor whose number is >= FD_SETSIZE (1024) and
        # raises "filedescriptor out of range in select()". A long-lived backend
        # that has accumulated many open fds hands newly opened ptys high fd
        # numbers, which would otherwise kill this reader thread — and so the
        # whole terminal — the instant it opened. poll(2) has no such limit.
        poller = select.poll()
        poller.register(primary_fd, select.POLLIN)

        while not self._stop_reader.is_set():
            try:
                # Wake on readable data (and, unsolicited, POLLHUP/POLLERR);
                # the 100ms timeout bounds how long we wait before re-checking
                # the stop flag. Any returned event funnels into os.read, whose
                # EOF/EIO handling below covers shell exit.
                if not poller.poll(100):
                    continue

                data = os.read(primary_fd, PTY_READ_BUFFER_SIZE)
                if not data:
                    # EOF - shell has exited
                    logger.debug("Pty EOF for environment {}", self._environment_id)
                    break

                self._emit_output(data)

            except OSError as e:
                if e.errno == errno.EIO:  # Terminal closed
                    logger.debug("Pty closed for environment {}", self._environment_id)
                    break
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):  # No data available (non-blocking)
                    continue
                logger.error("Pty read error for environment {}: {}", self._environment_id, e)
                break
            except Exception as e:
                logger.error("Unexpected error in pty reader: {}", e)
                break

        # The shell has exited — notify the user via the terminal output stream.
        # Use \r\n (carriage return + newline) for correct terminal rendering.
        self._emit_output(b"\r\n[Process exited]\r\n")

        # When the shell exits on its own (EOF/EIO — e.g. the user typed `exit`)
        # rather than because stop() asked the reader to stop, nothing else will
        # close the pty primary fd or unregister this manager: stop() only runs
        # on an explicit user action (closing the panel) or workspace teardown.
        # Without this, every self-exited shell leaks one pty primary fd until
        # then, pushing the long-lived backend toward the fd ceiling. Tear down
        # here — directly, NOT via stop(), because stop() joins the reader thread
        # and this IS the reader thread (joining itself would deadlock). The
        # cleanup helpers are idempotent, so a later stop() is still safe.
        if not self._stop_reader.is_set():
            logger.debug("Shell self-exited for environment {}; cleaning up pty", self._environment_id)
            self._unregister_from_registry()
            self._close_pty_process()

    def write(self, data: bytes) -> None:
        """Write data to the terminal.

        Args:
            data: The data to write to the terminal.
        """
        if self._pty_process is None or self._pty_process.primary_fd is None:
            logger.error("Cannot write to terminal - not started")
            return

        try:
            os.write(self._pty_process.primary_fd, data)
        except OSError as e:
            logger.error("Failed to write to pty: {}", e)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal.

        Args:
            rows: Number of rows.
            cols: Number of columns.
        """
        pty_process = self._pty_process
        if pty_process is None:
            return
        primary_fd = pty_process.primary_fd
        if primary_fd is None:
            return

        try:
            # TIOCSWINSZ = 0x5414 on Linux, but we use termios to be portable
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(primary_fd, termios.TIOCSWINSZ, winsize)
        except OSError as e:
            logger.error("Failed to resize pty: {}", e)

    def subscribe(self, callback: Callable[[bytes], None]) -> bytes:
        """Atomically snapshot the output buffer and register ``callback``.

        Returns the buffered output for session replay.  After this call, every
        future `_emit_output` invocation also fires ``callback``.  Holding the
        state lock across both operations is what prevents the "callback
        registered after new output was already buffered" race that would
        otherwise drop bytes produced during reconnect.
        """
        with self._state_lock:
            snapshot = b"".join(self._output_buffer)
            self._output_callbacks.append(callback)
            return snapshot

    def remove_output_callback(self, callback: Callable[[bytes], None]) -> None:
        """Remove an output callback.

        Args:
            callback: The callback to remove.
        """
        with self._state_lock:
            if callback in self._output_callbacks:
                self._output_callbacks.remove(callback)

    def _unregister_from_registry(self) -> None:
        """Remove this manager from the global registry, if it is the registered one.

        A duplicate manager (created during a race) should not remove the winner
        from the registry. Idempotent: a second call is a no-op once we are gone.
        """
        with _registry_lock:
            if _terminal_managers.get(self._terminal_id) is self:
                del _terminal_managers[self._terminal_id]

    def _close_pty_process(self) -> None:
        """Close the pty primary fd and terminate the shell process.

        Order matters: close the primary fd *first* so the kernel delivers
        SIGHUP to the foreground process group on the secondary side —
        interactive login shells (bash -l, zsh) explicitly install SIG_IGN for
        SIGTERM per POSIX (so that `kill 0` doesn't yank a user's session), but
        they DO honour SIGHUP and exit, propagating SIGHUP to their jobs.  This
        matches "user closed the terminal window" semantics and lets the shell
        tear down cleanly in milliseconds instead of waiting out the full
        SIGTERM grace period.  SIGTERM + SIGKILL via terminate() remains as a
        fallback for non-shell PTY children and for any shell that hasn't yet
        observed the hangup.

        Idempotent: ``close_primary_fd`` and ``terminate`` both no-op once the
        fd is closed / the shell is gone, and ``_pty_process`` is cleared so a
        second call returns immediately. This is what lets both stop() (external
        teardown) and _read_loop (the shell self-exited) call it safely.
        """
        pty_process = self._pty_process
        if pty_process is None:
            return
        pty_process.close_primary_fd()
        pty_process.terminate(force_kill_seconds=1.0)
        self._pty_process = None

    def stop(self) -> None:
        """Stop the terminal session."""
        logger.debug("Stopping terminal for environment {}", self._environment_id)

        self._unregister_from_registry()

        # Stop the reader thread before tearing down the pty so it is not
        # polling a primary fd we are about to close.
        self._stop_reader.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
            self._reader_thread = None

        self._close_pty_process()

        logger.debug("Terminal stopped for environment {}", self._environment_id)
