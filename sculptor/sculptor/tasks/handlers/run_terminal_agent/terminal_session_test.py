"""Tests for agent-scoped PTY sessions.

Spawns real ptys through a real ConcurrencyGroup (matching the
local_terminal_manager test precedent) — kept few because PTY spawning can
flake under heavy pytest parallelism.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import psutil
import pytest

from imbue_core.agents.data_types.ids import TaskID
from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    stop_terminals_for_environment,
)
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import AgentTerminalConfig
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import create_agent_terminal
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import get_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import make_agent_terminal_id
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import reap_stale_shell
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import register_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import render_resume_command
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import stop_agent_terminal
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import unregister_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import write_launch_command

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


def _register_config(task_id: TaskID, environment_id: str, directory: Path, group: ConcurrencyGroup) -> None:
    register_agent_terminal_config(
        task_id,
        AgentTerminalConfig(
            environment_id=environment_id,
            workspace_path=directory,
            working_directory=directory,
            concurrency_group=group,
            extra_env={},
            env_var_override=False,
            sculptor_folder=None,
        ),
    )


def test_make_agent_terminal_id_is_readable_and_task_scoped() -> None:
    task_id = TaskID()
    assert make_agent_terminal_id(task_id) == f"agent:{task_id}"


def test_create_agent_terminal_without_config_returns_none() -> None:
    assert create_agent_terminal(TaskID()) is None


def test_config_registry_round_trip() -> None:
    task_id = TaskID()
    with ConcurrencyGroup(name="agent-terminal-config-test") as group:
        _register_config(task_id, "env-config-test", Path("/tmp"), group)
        try:
            config = get_agent_terminal_config(task_id)
            assert config is not None
            assert config.environment_id == "env-config-test"
        finally:
            unregister_agent_terminal_config(task_id)
        assert get_agent_terminal_config(task_id) is None
        # Double-unregister is safe.
        unregister_agent_terminal_config(task_id)


def test_create_and_stop_agent_terminal(tmp_path: Path) -> None:
    task_id = TaskID()
    environment_id = "env-agent-terminal-test"
    terminal_id = make_agent_terminal_id(task_id)
    with ConcurrencyGroup(name="agent-terminal-test") as group:
        _register_config(task_id, environment_id, tmp_path, group)
        try:
            manager = create_agent_terminal(task_id)
            assert manager is not None
            assert get_terminal_manager(terminal_id) is manager
            # Registered under the workspace's environment id so
            # stop_terminals_for_environment remains the teardown backstop.
            assert manager._environment_id == environment_id

            # A second create returns the existing manager.
            assert create_agent_terminal(task_id) is manager

            stop_agent_terminal(task_id)
            assert get_terminal_manager(terminal_id) is None
            # Double-stop is safe.
            stop_agent_terminal(task_id)
        finally:
            stop_agent_terminal(task_id)
            unregister_agent_terminal_config(task_id)


def test_stop_terminals_for_environment_stops_agent_terminal(tmp_path: Path) -> None:
    task_id = TaskID()
    environment_id = "env-agent-backstop-test"
    terminal_id = make_agent_terminal_id(task_id)
    with ConcurrencyGroup(name="agent-terminal-backstop-test") as group:
        _register_config(task_id, environment_id, tmp_path, group)
        try:
            manager = create_agent_terminal(task_id)
            assert manager is not None

            stop_terminals_for_environment(environment_id)

            assert get_terminal_manager(terminal_id) is None
        finally:
            stop_agent_terminal(task_id)
            unregister_agent_terminal_config(task_id)


class _FakeSilentManager:
    """A manager whose shell never produces output (for the timeout fallback)."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.removed_callbacks: list[object] = []

    def subscribe(self, callback: object) -> bytes:
        del callback
        return b""

    def remove_output_callback(self, callback: object) -> None:
        self.removed_callbacks.append(callback)

    def write(self, data: bytes) -> None:
        self.writes.append(data)


def test_write_launch_command_waits_for_shell_output(tmp_path: Path) -> None:
    task_id = TaskID()
    with ConcurrencyGroup(name="launch-command-test") as group:
        _register_config(task_id, "env-launch-test", tmp_path, group)
        try:
            manager = create_agent_terminal(task_id)
            assert manager is not None

            write_launch_command(manager, "echo launched-marker", timeout_seconds=10.0)

            # The command executed in the shell: its output lands in the
            # replay buffer (poll — shell echo is asynchronous).
            buffered = b""
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                buffered = manager.subscribe(lambda _data: None)
                if b"launched-marker" in buffered:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError(f"launch command output never appeared; buffer: {buffered!r}")
        finally:
            stop_agent_terminal(task_id)
            unregister_agent_terminal_config(task_id)


def test_write_launch_command_times_out_and_writes_anyway() -> None:
    manager = _FakeSilentManager()

    write_launch_command(manager, "claude", timeout_seconds=0.05)  # pyre-ignore[6]

    assert manager.writes == [b"claude\n"]
    # The readiness callback must not leak.
    assert len(manager.removed_callbacks) == 1


def test_render_resume_command_replaces_and_quotes() -> None:
    assert render_resume_command("claude --resume {session_id}", "abc.123") == "claude --resume abc.123"
    # A charset-legal but odd-looking value stays inert (shlex quoting is the
    # second defense layer behind the API's charset validation).
    assert render_resume_command("claude --resume {session_id}", "a_b-c.D") == "claude --resume a_b-c.D"
    # No placeholder → the template is unchanged.
    assert render_resume_command("claude --continue", "abc") == "claude --continue"


def test_reap_stale_shell_ignores_nonexistent_pid() -> None:
    # A reaped child's pid no longer exists (Popen + wait reaps it).
    probe = subprocess.Popen(["true"])
    probe.wait(timeout=5)
    reap_stale_shell(probe.pid)  # must not raise


def test_reap_stale_shell_never_kills_a_non_session_leader() -> None:
    # A plain child process is NOT a session leader — the guard must skip it
    # even though the pid exists.
    child = subprocess.Popen(["sleep", "30"])
    try:
        reap_stale_shell(child.pid)
        assert child.poll() is None, "non-session-leader process must not be killed"
    finally:
        child.kill()
        child.wait(timeout=5)


def test_reap_stale_shell_kills_a_previous_runs_shell(tmp_path: Path) -> None:
    # A real PTY shell IS a session leader; fake "previous run" by patching
    # the backend's create_time to the future so the age guard passes.
    task_id = TaskID()
    with ConcurrencyGroup(name="reap-test") as group:
        _register_config(task_id, "env-reap-test", tmp_path, group)
        try:
            manager = create_agent_terminal(task_id)
            assert manager is not None
            shell_pid = manager.shell_pid
            assert shell_pid is not None
            assert os.getpgid(shell_pid) == shell_pid  # session leader

            backend_create_time = psutil.Process().create_time()
            with patch.object(psutil.Process, "create_time", autospec=True) as fake_create_time:

                def create_time_side_effect(self: psutil.Process) -> float:
                    if self.pid == os.getpid():
                        return backend_create_time + 10_000.0
                    return backend_create_time - 10_000.0

                fake_create_time.side_effect = create_time_side_effect
                reap_stale_shell(shell_pid)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if not psutil.pid_exists(shell_pid):
                    break
                time.sleep(0.05)
            else:
                raise AssertionError(f"stale shell {shell_pid} still alive after reap")
        finally:
            stop_agent_terminal(task_id)
            unregister_agent_terminal_config(task_id)
