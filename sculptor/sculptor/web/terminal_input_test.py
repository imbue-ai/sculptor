"""Tests for POST /api/v1/agents/{agent_id}/terminal/input (automated prompts).

The endpoint's guards exist to prevent one specific hazard: text written into
a program that would execute it (a bare shell) or mis-handle it (a TUI
mid-turn). Every 409 case here is one of those hazards.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import httpx
from fastapi.testclient import TestClient

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentSignalRunnerMessage
from sculptor.interfaces.agents.agent import TerminalStatusSignal
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    LocalTerminalManager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import make_agent_terminal_id
from sculptor.web.auth import authenticate_anonymous

_OPT_IN_CONFIG = RegisteredTerminalAgentConfig(
    registration_id="claude-code",
    display_name="Claude Code",
    launch_command="claude",
    accepts_automated_prompts=True,
)
_NO_OPT_IN_CONFIG = RegisteredTerminalAgentConfig(
    registration_id="some-tui",
    display_name="Some TUI",
    launch_command="some-tui",
    accepts_automated_prompts=False,
)


def _create_task(
    services: CompleteServiceCollection,
    project: Project,
    agent_config: RegisteredTerminalAgentConfig | TerminalAgentConfig | ClaudeCodeSDKAgentConfig,
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


def _seed_run_start(services: CompleteServiceCollection, task_id: TaskID) -> None:
    user_session = authenticate_anonymous(services, RequestID())
    message = EnvironmentAcquiredRunnerMessage.model_construct(
        message_id=AgentMessageID(),
        environment=None,
    )
    with user_session.open_transaction(services) as transaction:
        services.task_service.create_message(message, task_id, transaction)


def _seed_signal(services: CompleteServiceCollection, task_id: TaskID, signal: TerminalStatusSignal) -> None:
    user_session = authenticate_anonymous(services, RequestID())
    with user_session.open_transaction(services) as transaction:
        services.task_service.create_message(TerminalAgentSignalRunnerMessage(signal=signal), task_id, transaction)


class _RecordingTerminalManager(LocalTerminalManager):
    """Never started: records write() bytes instead of touching a pty."""

    def __init__(self, terminal_id: str, tmp_path: Path, concurrency_group: ConcurrencyGroup) -> None:
        super().__init__(
            environment_id="terminal-input-test-env",
            workspace_path=tmp_path,
            working_directory=tmp_path,
            concurrency_group=concurrency_group,
            terminal_id=terminal_id,
        )
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)


@contextmanager
def _registered_manager(task_id: TaskID, tmp_path: Path) -> Generator[_RecordingTerminalManager, None, None]:
    terminal_id = make_agent_terminal_id(task_id)
    with ConcurrencyGroup(name="terminal-input-test") as concurrency_group:
        manager = _RecordingTerminalManager(terminal_id, tmp_path, concurrency_group)
        register_terminal_manager(terminal_id, manager)
        try:
            yield manager
        finally:
            unregister_terminal_manager(terminal_id)


def _post_input(client: TestClient, task: Task, body: dict) -> httpx.Response:
    return client.post(f"/api/v1/agents/{task.object_id}/terminal/input", json=body)


def test_single_line_prompt_writes_text_and_submit(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "Commit the changes"})
        assert response.status_code == 204, response.text
        assert manager.written == [b"Commit the changes\r"]


def test_single_line_without_submit_omits_carriage_return(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "draft only", "submit": False})
        assert response.status_code == 204, response.text
        assert manager.written == [b"draft only"]


def test_multi_line_prompt_is_bracketed_paste_then_submit(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "line one\nline two"})
        assert response.status_code == 204, response.text
        # Exact bytes: paste block in one write (the TUI must not submit on
        # the embedded newline), then the Enter as a separate write.
        assert manager.written == [b"\x1b[200~line one\nline two\x1b[201~", b"\r"]


def test_multi_line_without_submit_writes_only_the_paste_block(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "a\nb", "submit": False})
        assert response.status_code == 204, response.text
        assert manager.written == [b"\x1b[200~a\nb\x1b[201~"]


def test_waiting_signal_allows_input(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    # Answering a program's question is a primary use case.
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.WAITING)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "yes"})
        assert response.status_code == 204, response.text
        assert manager.written == [b"yes\r"]


def test_plain_terminal_never_receives_writes(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    # A bare shell would EXECUTE the prompt as commands — always 409, even
    # with a live manager and an idle-looking message history.
    services = test_already_started_services
    task = _create_task(services, test_project, TerminalAgentConfig())
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "echo pwned"})
        assert response.status_code == 409
        assert manager.written == []


def test_registered_agent_without_opt_in_is_rejected(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _NO_OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "hello"})
        assert response.status_code == 409
        assert manager.written == []


def test_busy_agent_is_rejected(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.BUSY)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "hello"})
        assert response.status_code == 409
        assert manager.written == []


def test_no_signals_this_run_is_rejected(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    # Run started but the program's hooks have said nothing: broken hooks
    # degrade a registered agent to plain-terminal behavior, so the state is
    # unknown and writes are refused.
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "hello"})
        assert response.status_code == 409
        assert manager.written == []


def test_signal_from_previous_run_is_rejected(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    # An IDLE from before the latest run start says nothing about the
    # relaunched program.
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)
    _seed_run_start(services, task.object_id)

    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": "hello"})
        assert response.status_code == 409
        assert manager.written == []


def test_no_live_terminal_is_rejected(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    response = _post_input(client, task, {"text": "hello"})
    assert response.status_code == 409


def test_chat_and_unknown_agents_are_404(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services
    chat_task = _create_task(services, test_project, ClaudeCodeSDKAgentConfig())
    assert _post_input(client, chat_task, {"text": "hello"}).status_code == 404

    assert client.post(f"/api/v1/agents/{TaskID()}/terminal/input", json={"text": "hello"}).status_code == 404
