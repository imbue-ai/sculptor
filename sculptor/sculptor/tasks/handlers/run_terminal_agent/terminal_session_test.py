"""Tests for agent-scoped PTY sessions.

Spawns real ptys through a real ConcurrencyGroup (matching the
local_terminal_manager test precedent) — kept few because PTY spawning can
flake under heavy pytest parallelism.
"""

import sys
from pathlib import Path

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
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import register_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import stop_agent_terminal
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import unregister_agent_terminal_config

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
