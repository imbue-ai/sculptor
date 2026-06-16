"""Tests for POST /api/v1/agents/{agent_id}/signal (terminal-agent signals)."""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentSignalRunnerMessage
from sculptor.interfaces.agents.agent import TerminalStatusSignal
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.state.messages import Message
from sculptor.web.auth import authenticate_anonymous


def _create_task(
    services: CompleteServiceCollection,
    project: Project,
    agent_config: TerminalAgentConfig | ClaudeCodeSDKAgentConfig,
    title: str | None = None,
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
        current_state=AgentTaskStateV2(workspace_id=WorkspaceID(), title=title),
        outcome=TaskState.RUNNING,
    )
    with user_session.open_transaction(services) as transaction:
        services.task_service.create_task(task, transaction)
    return task


def _mark_task_deleted(services: CompleteServiceCollection, task_id: TaskID) -> None:
    data_model_service = services.data_model_service
    assert isinstance(data_model_service, TaskDataModelService)
    with data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task_id)
        assert task_row is not None
        transaction.upsert_task(task_row.evolve(task_row.ref().is_deleted, True))


def _post_signal(client: TestClient, task: Task, body: dict) -> httpx.Response:
    return client.post(f"/api/v1/agents/{task.object_id}/signal", json=body)


def _live_messages(services: CompleteServiceCollection, task_id: TaskID) -> list[Message]:
    messages: list[Message] = []
    with services.task_service.subscribe_to_task(task_id) as queue:
        while queue.qsize() > 0:
            messages.append(queue.get_nowait())
    return messages


def _current_state(services: CompleteServiceCollection, task_id: TaskID) -> AgentTaskStateV2:
    user_session = authenticate_anonymous(services, RequestID())
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(task_id, transaction)
    assert task is not None
    return AgentTaskStateV2.model_validate(task.current_state)


@pytest.mark.parametrize(
    ("event", "expected_signal"),
    [
        ("busy", TerminalStatusSignal.BUSY),
        ("idle", TerminalStatusSignal.IDLE),
        ("waiting-on-input", TerminalStatusSignal.WAITING),
    ],
)
def test_status_events_become_ephemeral_signal_messages(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    event: str,
    expected_signal: TerminalStatusSignal,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, TerminalAgentConfig())

    response = _post_signal(client, task, {"event": event})
    assert response.status_code == 204, response.text

    # Visible on a live subscription (replayed to new subscribers)...
    signals = [m for m in _live_messages(services, task.object_id) if isinstance(m, TerminalAgentSignalRunnerMessage)]
    assert [s.signal for s in signals] == [expected_signal]

    # ...but never persisted (run-scoped: gone after a backend restart).
    user_session = authenticate_anonymous(services, RequestID())
    with user_session.open_transaction(services) as transaction:
        saved = services.task_service.get_saved_messages_for_task(task.object_id, transaction)
    assert not any(isinstance(m, TerminalAgentSignalRunnerMessage) for m in saved)


def test_files_changed_refreshes_workspace_diff(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, TerminalAgentConfig())
    refreshed: list[Any] = []

    def fake_refresh(self: DefaultWorkspaceService, workspace_id: Any) -> None:
        refreshed.append(workspace_id)

    original = DefaultWorkspaceService.maybe_refresh_workspace_diff
    DefaultWorkspaceService.maybe_refresh_workspace_diff = fake_refresh
    try:
        response = _post_signal(client, task, {"event": "files-changed"})
    finally:
        DefaultWorkspaceService.maybe_refresh_workspace_diff = original

    assert response.status_code == 204, response.text
    assert isinstance(task.current_state, AgentTaskStateV2)
    assert refreshed == [task.current_state.workspace_id]
    # files-changed is an event, not a status — no signal message emitted.
    assert not any(isinstance(m, TerminalAgentSignalRunnerMessage) for m in _live_messages(services, task.object_id))


def test_session_id_is_validated_and_persisted_without_clobbering_title(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, TerminalAgentConfig(), title="My Terminal")

    response = _post_signal(client, task, {"event": "session-id", "sessionId": "abc-123_X.z"})
    assert response.status_code == 204, response.text

    state = _current_state(services, task.object_id)
    assert state.terminal_session_id == "abc-123_X.z"
    assert state.title == "My Terminal"


@pytest.mark.parametrize(
    "bad_session_id",
    [
        None,
        "",
        "; rm -rf /",
        "a b",
        "$(touch pwned)",
        "x" * 129,
    ],
)
def test_session_id_rejects_unsafe_values(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    bad_session_id: str | None,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, TerminalAgentConfig())

    body: dict = {"event": "session-id"}
    if bad_session_id is not None:
        body["sessionId"] = bad_session_id
    response = _post_signal(client, task, body)

    assert response.status_code == 422
    assert _current_state(services, task.object_id).terminal_session_id is None


def test_unknown_event_is_ignored_with_204(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, TerminalAgentConfig())

    response = _post_signal(client, task, {"event": "frobnicate"})

    assert response.status_code == 204, response.text
    assert not any(isinstance(m, TerminalAgentSignalRunnerMessage) for m in _live_messages(services, task.object_id))


def test_signal_rejects_chat_and_deleted_and_unknown_agents(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services

    chat_task = _create_task(services, test_project, ClaudeCodeSDKAgentConfig())
    assert _post_signal(client, chat_task, {"event": "busy"}).status_code == 404

    deleted_task = _create_task(services, test_project, TerminalAgentConfig())
    _mark_task_deleted(services, deleted_task.object_id)
    assert _post_signal(client, deleted_task, {"event": "busy"}).status_code == 404

    assert client.post(f"/api/v1/agents/{TaskID()}/signal", json={"event": "busy"}).status_code == 404
