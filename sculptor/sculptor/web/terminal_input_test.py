"""Tests for POST /api/v1/agents/{agent_id}/terminal/input (automated prompts).

The endpoint's guards exist to prevent one specific hazard: text written into
a program that would execute it (a bare shell) or mis-handle it (a TUI
mid-turn). Every 409 case here is one of those hazards.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import httpx
import pytest
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
from sculptor.web import terminal_input
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.terminal_input import TerminalDeliveryResult
from sculptor.web.terminal_input import deliver_prompt_to_terminal_agent


@pytest.fixture(autouse=True)
def _no_real_paste_submit_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper pauses between the paste and the submit Enter in production;
    skip the real wait in tests (the one test that asserts the pause overrides
    this with its own recorder)."""
    monkeypatch.setattr(terminal_input.time, "sleep", lambda _seconds: None)


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


def test_single_line_prompt_is_bracketed_paste_then_separate_submit(
    client: TestClient,
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    # Regression (the CI Babysitter left its prompt unsubmitted with a trailing
    # newline): a single-line prompt must NOT glue the submit carriage return
    # onto the prompt text in one PTY write. A real TUI (Claude Code) treats a
    # large single-burst write as a paste and swallows a trailing CR as a
    # literal newline instead of Enter, so the prompt sits in the composer
    # unsubmitted. (A short "Hi" stays under the paste threshold, which is why
    # only longer prompts broke.) The body goes out as a bracketed paste and
    # the Enter is its own write — identical framing to the multi-line path.
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    prompt = "Investigate the failing pipeline for this MR, identify the root cause, fix the code, commit, and push."
    with _registered_manager(task.object_id, tmp_path) as manager:
        response = _post_input(client, task, {"text": prompt})
        assert response.status_code == 204, response.text
        assert manager.written == [b"\x1b[200~" + prompt.encode() + b"\x1b[201~", b"\r"]


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
        # Body is bracketed-pasted into the composer; no Enter, so it's a draft.
        assert manager.written == [b"\x1b[200~draft only\x1b[201~"]


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
        assert manager.written == [b"\x1b[200~yes\x1b[201~", b"\r"]


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


# Direct unit tests for the shared helper that both the endpoint above and the
# CI Babysitter call. The endpoint tests exercise the helper through HTTP; these
# pin the helper's result enum and bytes directly, so the babysitter caller
# (which maps results to a transient reason, not an HTTP status) is covered too.


def test_helper_rejects_non_opt_in_config(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _NO_OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        result = deliver_prompt_to_terminal_agent(task, "hello", task_service=services.task_service)
        assert result is TerminalDeliveryResult.NOT_OPT_IN
        assert manager.written == []


def test_helper_rejects_when_not_at_prompt(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.BUSY)

    with _registered_manager(task.object_id, tmp_path) as manager:
        result = deliver_prompt_to_terminal_agent(task, "hello", task_service=services.task_service)
        assert result is TerminalDeliveryResult.NOT_AT_PROMPT
        assert manager.written == []


def test_helper_reports_no_pty_when_terminal_missing(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    result = deliver_prompt_to_terminal_agent(task, "hello", task_service=services.task_service)
    assert result is TerminalDeliveryResult.NO_PTY


def test_submit_carriage_return_is_paused_after_the_paste(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The submit Enter must be written only AFTER a pause that follows the
    # bracketed-paste body. A real TUI (Claude Code) shows "Pasting text…" while
    # it finalizes a bracketed paste; an Enter that arrives in that window is
    # absorbed into the paste instead of submitting it, so the prompt never
    # lands / the driven turn never completes (the agent shows as perpetually
    # running). Verified against real claude: the back-to-back write fails and a
    # short pause fixes it. This pins the pause to occur between the body write
    # and the carriage-return write.
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        # Record (duration, writes-so-far) at each sleep so we can prove the
        # pause lands after the body and before the Enter.
        paused: list[tuple[float, int]] = []
        monkeypatch.setattr(terminal_input.time, "sleep", lambda s: paused.append((s, len(manager.written))))

        result = deliver_prompt_to_terminal_agent(task, "hello", task_service=services.task_service)

        assert result is TerminalDeliveryResult.DELIVERED
        assert manager.written == [b"\x1b[200~hello\x1b[201~", b"\r"]
        # Exactly one pause, of the configured duration, after the body write
        # (1 write done) and before the Enter.
        assert paused == [(terminal_input._PASTE_SUBMIT_DELAY_SECONDS, 1)]


def test_draft_without_submit_does_not_pause(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No Enter is sent for a draft, so there is nothing to pause for.
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        paused: list[float] = []
        monkeypatch.setattr(terminal_input.time, "sleep", lambda s: paused.append(s))
        result = deliver_prompt_to_terminal_agent(task, "draft", submit=False, task_service=services.task_service)
        assert result is TerminalDeliveryResult.DELIVERED
        assert manager.written == [b"\x1b[200~draft\x1b[201~"]
        assert paused == []


def test_helper_delivers_multiline_with_bracketed_paste(
    test_already_started_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    services = test_already_started_services
    task = _create_task(services, test_project, _OPT_IN_CONFIG)
    _seed_run_start(services, task.object_id)
    _seed_signal(services, task.object_id, TerminalStatusSignal.IDLE)

    with _registered_manager(task.object_id, tmp_path) as manager:
        result = deliver_prompt_to_terminal_agent(task, "line one\nline two", task_service=services.task_service)
        assert result is TerminalDeliveryResult.DELIVERED
        assert manager.written == [b"\x1b[200~line one\nline two\x1b[201~", b"\r"]
