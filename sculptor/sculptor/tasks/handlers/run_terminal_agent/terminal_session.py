"""Agent-scoped PTY sessions for terminal agents.

A terminal agent owns one PTY, registered in the shared terminal-manager
registry under ``agent:<task_id>`` — a readable, collision-free key beside
the 16-hex-char workspace terminal ids. The manager is constructed with the
workspace's *environment id*, so ``stop_terminals_for_environment`` remains
the teardown backstop.

The config registry mirrors ``register_environment_config`` in
``local_terminal_manager.py``: the task handler registers an
`AgentTerminalConfig` up front so the PTY can be (re)created on demand —
eagerly by the handler, and again by the terminal WebSocket route after a
shell self-exit.
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import signal
import threading
from pathlib import Path

import psutil
from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import TaskID
from sculptor.services.workspace_service.environment_manager.env_file_parser import load_project_env_vars
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    LocalTerminalManager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)


def make_agent_terminal_id(task_id: TaskID) -> str:
    """The registry key for a terminal agent's PTY."""
    return f"agent:{task_id}"


@dataclasses.dataclass(frozen=True)
class AgentTerminalConfig:
    """Everything needed to (re)create a terminal agent's PTY.

    Project env vars are NOT cached here — they are re-read at terminal
    creation time (matching `TerminalEnvironmentConfig`). ``extra_env`` holds
    only the static SCULPT_* vars the task handler injects.
    """

    environment_id: str
    workspace_path: Path
    working_directory: Path
    concurrency_group: ConcurrencyGroup
    extra_env: dict[str, str]
    env_var_override: bool
    sculptor_folder: Path | None


_agent_terminal_configs: dict[str, AgentTerminalConfig] = {}
_configs_lock = threading.Lock()


def register_agent_terminal_config(task_id: TaskID, config: AgentTerminalConfig) -> None:
    with _configs_lock:
        _agent_terminal_configs[str(task_id)] = config


def get_agent_terminal_config(task_id: TaskID) -> AgentTerminalConfig | None:
    with _configs_lock:
        return _agent_terminal_configs.get(str(task_id))


def unregister_agent_terminal_config(task_id: TaskID) -> None:
    with _configs_lock:
        _agent_terminal_configs.pop(str(task_id), None)


def create_agent_terminal(task_id: TaskID) -> LocalTerminalManager | None:
    """Create (or return the existing) PTY for a terminal agent.

    Returns None if no config is registered or the PTY fails to start. The
    manager is only registered after start() succeeds, so callers can assume
    any manager in the registry has a live pty.
    """
    config = get_agent_terminal_config(task_id)
    if config is None:
        return None

    terminal_id = make_agent_terminal_id(task_id)

    existing = get_terminal_manager(terminal_id)
    if existing is not None:
        return existing

    # Re-read project env vars from disk so a respawned shell sees changes the
    # user made to ~/.sculptor/.env or .sculptor/.env after the agent started.
    project_env = load_project_env_vars(config.working_directory, sculptor_folder=config.sculptor_folder)
    terminal_extra_env = {**project_env, **config.extra_env}

    manager = LocalTerminalManager(
        environment_id=config.environment_id,
        workspace_path=config.workspace_path,
        working_directory=config.working_directory,
        concurrency_group=config.concurrency_group,
        extra_env=terminal_extra_env,
        env_var_override=config.env_var_override,
        terminal_id=terminal_id,
    )

    try:
        manager.start()
    except Exception as e:
        # Recoverable: the caller returns None and the connection is retried.
        logger.debug("Failed to start agent terminal for task {}: {}", task_id, e)
        return None

    winner = register_terminal_manager(terminal_id, manager)
    if winner is not manager:
        # Another thread won the race — stop our duplicate.
        manager.stop()
    return winner


def stop_agent_terminal(task_id: TaskID) -> None:
    """Stop and unregister the agent's PTY, if any.

    Safe when the shell already self-exited (the reader thread unregistered
    the manager) and safe to call twice.
    """
    manager = unregister_terminal_manager(make_agent_terminal_id(task_id))
    if manager is not None:
        manager.stop()


def render_resume_command(template: str, session_id: str) -> str:
    """Render a registration's resume template with the reported session id.

    `str.replace`, NOT `.format` — a template containing other braces must
    not crash (the loader already validates this; belt-and-suspenders).
    `shlex.quote` even though the API-validated charset
    ([A-Za-z0-9._-]{1,128}) can't currently contain shell metacharacters —
    two independent layers of defense.
    """
    return template.replace("{session_id}", shlex.quote(session_id))


_REAP_SIGHUP_WAIT_SECONDS = 1.0


def reap_stale_shell(pid: int) -> None:
    """Kill a crash-surviving shell from a previous run, if it is provably ours.

    Guard order matters — a recycled pid must never be signalled:
    1. the pid exists;
    2. it is a session leader (our shells come from pty.fork(), so
       pgid == pid; a recycled pid is almost never one);
    3. it predates this backend process (a shell we spawned in a previous
       run cannot be younger than the current backend).
    Then SIGHUP the process group (closing-the-terminal semantics), with a
    SIGKILL fallback after a short wait.
    """
    try:
        if not psutil.pid_exists(pid):
            return
        if os.getpgid(pid) != pid:
            logger.debug("Not reaping pid {}: not a session leader (recycled pid?)", pid)
            return
        process = psutil.Process(pid)
        if process.create_time() >= psutil.Process().create_time():
            logger.debug("Not reaping pid {}: younger than this backend (recycled pid?)", pid)
            return
        logger.info("Reaping stale terminal-agent shell {} from a previous run", pid)
        os.killpg(pid, signal.SIGHUP)
        try:
            process.wait(timeout=_REAP_SIGHUP_WAIT_SECONDS)
        except psutil.TimeoutExpired:
            os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, psutil.NoSuchProcess):
        logger.debug("Stale shell {} disappeared during reaping", pid)
    except PermissionError:
        # macOS raises this for foreign processes — treat as "not ours".
        logger.debug("No permission to inspect/signal pid {}; skipping reap", pid)


def write_launch_command(manager: LocalTerminalManager, command: str, timeout_seconds: float = 5.0) -> None:
    """Write a registered program's launch command into the shell, as if typed.

    Waits for the shell's first output bytes (the prompt — or at least rc-file
    noise — has printed) before writing, so the keystrokes aren't swallowed by
    shell init. On timeout the command is written
    anyway: the program runs as a shell job either way, and a slightly-late
    write still works. The command comes from a user-authored registration —
    the same trust level as the user typing into their own shell.
    """
    ready = threading.Event()

    def on_output(_data: bytes) -> None:
        ready.set()

    # subscribe() atomically snapshots the buffer AND registers the callback,
    # so output between "check" and "register" can't be missed.
    snapshot = manager.subscribe(on_output)
    try:
        if not snapshot and not ready.wait(timeout_seconds):
            logger.debug("Shell produced no output within {}s; writing launch command anyway", timeout_seconds)
    finally:
        manager.remove_output_callback(on_output)
    manager.write((command + "\n").encode())
