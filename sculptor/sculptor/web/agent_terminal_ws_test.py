"""Tests for the agent-scoped terminal WebSocket route.

Validation paths assert the 4404 close-frame contract the frontend's retry
logic depends on. The live path (xterm round-trip) is covered by the
terminal-agent integration tests; here we only assert connection acceptance
and the respawn-on-demand behavior with a real (but short-lived) pty.
"""

import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import AgentTerminalConfig
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import make_agent_terminal_id
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import register_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import stop_agent_terminal
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import unregister_agent_terminal_config
from sculptor.web.auth import authenticate_anonymous

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


def _create_task(
    services: CompleteServiceCollection,
    project: Project,
    agent_config: TerminalAgentConfig | ClaudeCodeSDKAgentConfig,
) -> Task:
    user_session = authenticate_anonymous(services, RequestID())
    task = Task(
        object_id=TaskID(),
        organization_reference=user_session.organization_reference,
        user_reference=UserReference("usr_123"),
        project_id=project.object_id,
        input_data=AgentTaskInputsV2(
            agent_config=agent_config,
            git_hash="initialhash",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=WorkspaceID()),
        outcome=TaskState.RUNNING,
    )
    with user_session.open_transaction(services) as transaction:
        services.task_service.create_task(task, transaction)
    return task


def _expect_4404(client: TestClient, url: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(url) as ws:
            ws.receive_bytes()
    assert exc_info.value.code == 4404


def test_agent_terminal_ws_4404_for_malformed_id(client: TestClient) -> None:
    _expect_4404(client, "/api/v1/agents/not-a-task-id/terminal/ws")


def test_agent_terminal_ws_4404_for_unknown_agent(client: TestClient) -> None:
    _expect_4404(client, f"/api/v1/agents/{TaskID()}/terminal/ws")


def test_agent_terminal_ws_4404_for_chat_agent(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    task = _create_task(test_already_started_services, test_project, ClaudeCodeSDKAgentConfig())
    _expect_4404(client, f"/api/v1/agents/{task.object_id}/terminal/ws")


def test_agent_terminal_ws_4404_when_handler_not_running(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    # A terminal-agent task with no registered AgentTerminalConfig (its task
    # handler is not running) cannot spawn a PTY — the client should retry.
    task = _create_task(test_already_started_services, test_project, TerminalAgentConfig())
    _expect_4404(client, f"/api/v1/agents/{task.object_id}/terminal/ws")


@pytest.fixture
def terminal_agent_with_config(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> Iterator[Task]:
    task = _create_task(test_already_started_services, test_project, TerminalAgentConfig())
    with ConcurrencyGroup(name="agent-terminal-ws-test") as group:
        register_agent_terminal_config(
            task.object_id,
            AgentTerminalConfig(
                environment_id="env-agent-terminal-ws-test",
                workspace_path=tmp_path,
                working_directory=tmp_path,
                concurrency_group=group,
                extra_env={},
                env_var_override=False,
                sculptor_folder=None,
            ),
        )
        try:
            yield task
        finally:
            stop_agent_terminal(task.object_id)
            unregister_agent_terminal_config(task.object_id)


def test_agent_terminal_ws_connects_and_respawns_fresh_shell(
    client: TestClient,
    terminal_agent_with_config: Task,
) -> None:
    task = terminal_agent_with_config
    terminal_id = make_agent_terminal_id(task.object_id)
    url = f"/api/v1/agents/{task.object_id}/terminal/ws"

    # First connection spawns the PTY on demand (no eager spawn ran here).
    with client.websocket_connect(url):
        first_manager = get_terminal_manager(terminal_id)
        assert first_manager is not None

    # The PTY survives the WebSocket disconnect.
    assert get_terminal_manager(terminal_id) is first_manager

    # Simulate the shell going away (e.g. the user typed `exit`).
    stop_agent_terminal(task.object_id)
    assert get_terminal_manager(terminal_id) is None

    # Reconnecting respawns a fresh shell — a different manager object.
    with client.websocket_connect(url):
        second_manager = get_terminal_manager(terminal_id)
        assert second_manager is not None
        assert second_manager is not first_manager
