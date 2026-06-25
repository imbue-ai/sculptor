"""Tests for the terminal-agent task handler."""

import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest

from sculptor.common.plugin import get_plugins_base_dir
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentReleasedRunnerMessage
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LOCAL_WORKSPACE_DIR
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.state.messages import Message
from sculptor.tasks.api import run_task
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import get_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import make_agent_terminal_id
from sculptor.tasks.handlers.run_terminal_agent.v1 import _run_terminal_agent_in_environment
from sculptor.tasks.handlers.run_terminal_agent.v1 import launch_command_for_start
from sculptor.tasks.handlers.run_terminal_agent.v1 import run_terminal_agent_task_v1


@pytest.fixture
def project() -> Project:
    return Project(object_id=ProjectID(), name="Test Project", organization_reference=OrganizationReference("org_123"))


@pytest.fixture
def terminal_task(project: Project) -> Task:
    return Task(
        object_id=TaskID(),
        organization_reference=project.organization_reference,
        user_reference=UserReference("usr_123"),
        project_id=project.object_id,
        input_data=AgentTaskInputsV2(
            agent_config=TerminalAgentConfig(),
            git_hash="initialhash",
            system_prompt=None,
        ),
    )


@pytest.fixture
def services(
    test_service_collection: CompleteServiceCollection,
    terminal_task: Task,
    project: Project,
) -> Generator[ServiceCollectionForTask, None, None]:
    with test_service_collection.data_model_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_project(project)
        test_service_collection.task_service.create_task(terminal_task, transaction)
    yield cast(ServiceCollectionForTask, test_service_collection)


@pytest.fixture
def environment(
    project: Project,
    initial_commit_repo: tuple[Path, str],
    test_root_concurrency_group: ConcurrencyGroup,
) -> Generator[LocalEnvironment, None, None]:
    code_dir, _ = initial_commit_repo
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    workspace_dir.mkdir(parents=True, exist_ok=True)

    environment = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(workspace_dir)),
        project_id=project.object_id,
        concurrency_group=test_root_concurrency_group,
        repo_host_path=code_dir,
    )
    try:
        yield environment
    finally:
        environment.close()


def _set_task_state(task: Task, state: AgentTaskStateV2, services: ServiceCollectionForTask) -> None:
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task.object_id)
        assert task_row is not None
        updated = task_row.evolve(task_row.ref().current_state, state.model_dump())
        transaction.upsert_task(updated)


def _get_all_messages(task_id: TaskID, services: ServiceCollectionForTask) -> list[Message]:
    all_messages: list[Message] = []
    with services.task_service.subscribe_to_task(task_id) as queue:
        while queue.qsize() > 0:
            all_messages.append(queue.get_nowait())
    return all_messages


def test_terminal_handler_spawns_pty_and_pauses_on_shutdown(
    terminal_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """The loop spawns the agent PTY, then shutdown re-queues and cleans up."""
    workspace_id = WorkspaceID()
    task_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(terminal_task, task_state, services)
    shutdown_event = threading.Event()
    terminal_id = make_agent_terminal_id(terminal_task.object_id)
    seen_managers: list[Any] = []

    def watch_then_shutdown() -> None:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            manager = get_terminal_manager(terminal_id)
            if manager is not None:
                seen_managers.append(manager)
                break
            time.sleep(0.05)
        shutdown_event.set()

    watcher = threading.Thread(target=watch_then_shutdown, daemon=True)
    watcher.start()
    with pytest.raises(UserPausedTaskError):
        _run_terminal_agent_in_environment(
            task=terminal_task,
            task_state=task_state,
            project=project,
            underlying_env=environment,
            environment_concurrency_group=test_root_concurrency_group,
            services=services,
            settings=test_settings,
            shutdown_event=cast(ReadOnlyEvent, shutdown_event),
            on_started=None,
        )
    watcher.join(timeout=5.0)

    assert seen_managers, "PTY manager was never registered while the loop ran"
    # The shell env carries the agent identity (spawned with extra_env).
    assert seen_managers[0]._extra_env["SCULPT_AGENT_ID"] == str(terminal_task.object_id)
    assert "SCULPT_API_PORT" in seen_managers[0]._extra_env
    assert "SCULPT_WORKSPACE_ID" in seen_managers[0]._extra_env
    assert "SCULPT_PROJECT_ID" in seen_managers[0]._extra_env
    assert "PATH" in seen_managers[0]._extra_env
    # Registration launch commands shell-expand these (install-relative paths
    # cannot be baked into registration files).
    assert seen_managers[0]._extra_env["SCULPT_PLUGINS_DIR"] == str(get_plugins_base_dir())
    # No claude_binary_path passed above → the PATH fallback.
    assert seen_managers[0]._extra_env["SCULPT_CLAUDE_BIN"] == "claude"
    # Cleanup: manager and config are gone after the loop exits.
    assert get_terminal_manager(terminal_id) is None
    assert get_agent_terminal_config(terminal_task.object_id) is None


def test_outer_handler_emits_acquired_and_released_messages(
    terminal_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """run_terminal_agent_task_v1 mirrors the chat handler's runner messages."""
    workspace_id = WorkspaceID()
    _set_task_state(terminal_task, AgentTaskStateV2(workspace_id=workspace_id), services)
    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=terminal_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )

    @contextmanager
    def fake_environment_context(self: DefaultWorkspaceService, **kwargs: Any) -> Generator[Any, None, None]:
        yield agent_env

    def fake_inner(**kwargs: Any) -> None:
        raise UserPausedTaskError()

    shutdown_event = threading.Event()
    task_data = terminal_task.input_data
    assert isinstance(task_data, AgentTaskInputsV2)
    with (
        patch.object(DefaultWorkspaceService, "agent_environment_context", fake_environment_context),
        patch.object(DefaultWorkspaceService, "mark_workspace_diff_stale", lambda self, workspace_id: None),
        patch(
            "sculptor.tasks.handlers.run_terminal_agent.v1._run_terminal_agent_in_environment",
            side_effect=fake_inner,
        ),
    ):
        with pytest.raises(UserPausedTaskError):
            run_terminal_agent_task_v1(
                task_data,
                terminal_task,
                services,
                None,
                test_settings,
                test_root_concurrency_group,
                cast(ReadOnlyEvent, shutdown_event),
                None,
            )

    messages = _get_all_messages(terminal_task.object_id, services)
    assert any(isinstance(m, EnvironmentAcquiredRunnerMessage) for m in messages)
    assert any(isinstance(m, EnvironmentReleasedRunnerMessage) for m in messages)


def test_run_task_dispatches_terminal_config_to_terminal_handler(
    terminal_task: Task,
    services: ServiceCollectionForTask,
    test_settings: SculptorSettings,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    shutdown_event = threading.Event()
    with (
        patch("sculptor.tasks.api.run_terminal_agent_task_v1", return_value=None) as terminal_handler,
        patch("sculptor.tasks.api.run_agent_task_v1", return_value=None) as chat_handler,
    ):
        run_task(
            terminal_task,
            services,
            None,
            test_settings,
            test_root_concurrency_group,
            cast(ReadOnlyEvent, shutdown_event),
            None,
        )
    terminal_handler.assert_called_once()
    chat_handler.assert_not_called()


def test_launch_command_for_start_selects_per_config() -> None:
    state = AgentTaskStateV2(workspace_id=WorkspaceID())
    state_with_session = AgentTaskStateV2(workspace_id=WorkspaceID(), terminal_session_id="sess-42")
    plain = AgentTaskInputsV2(agent_config=TerminalAgentConfig(), git_hash="x")
    # Plain terminals always get a bare shell — also after restart.
    assert launch_command_for_start(plain, state) is None
    assert launch_command_for_start(plain, state_with_session) is None

    registered = AgentTaskInputsV2(
        agent_config=RegisteredTerminalAgentConfig(
            registration_id="claude-code",
            display_name="Claude Code",
            launch_command="claude",
            resume_command_template="claude --resume {session_id}",
        ),
        git_hash="x",
    )
    # No session reported yet → plain launch.
    assert launch_command_for_start(registered, state) == "claude"
    # Session + template → rendered resume command.
    assert launch_command_for_start(registered, state_with_session) == "claude --resume sess-42"

    registered_no_template = AgentTaskInputsV2(
        agent_config=RegisteredTerminalAgentConfig(
            registration_id="claude-code",
            display_name="Claude Code",
            launch_command="claude",
        ),
        git_hash="x",
    )
    # Session but no template → plain launch.
    assert launch_command_for_start(registered_no_template, state_with_session) == "claude"


def test_registered_config_launch_command_is_written_on_spawn(
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """A registered agent's handler writes the stamped launch command into the
    shell exactly once; plain terminal agents write nothing."""
    user_session_task = Task(
        object_id=TaskID(),
        organization_reference=project.organization_reference,
        user_reference=UserReference("usr_123"),
        project_id=project.object_id,
        input_data=AgentTaskInputsV2(
            agent_config=RegisteredTerminalAgentConfig(
                registration_id="claude-code",
                display_name="Claude Code",
                launch_command="echo registered-launch-marker",
            ),
            git_hash="initialhash",
        ),
    )
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        services.task_service.create_task(user_session_task, transaction)

    task_state = AgentTaskStateV2(workspace_id=WorkspaceID())
    _set_task_state(user_session_task, task_state, services)
    shutdown_event = threading.Event()
    written_commands: list[str] = []

    def fake_write_launch_command(manager: Any, command: str, timeout_seconds: float = 5.0) -> None:
        del manager, timeout_seconds
        written_commands.append(command)
        shutdown_event.set()

    with patch(
        "sculptor.tasks.handlers.run_terminal_agent.v1.write_launch_command",
        side_effect=fake_write_launch_command,
    ):
        with pytest.raises(UserPausedTaskError):
            _run_terminal_agent_in_environment(
                task=user_session_task,
                task_state=task_state,
                project=project,
                underlying_env=environment,
                environment_concurrency_group=test_root_concurrency_group,
                services=services,
                settings=test_settings,
                shutdown_event=shutdown_event,
                on_started=None,
            )

    assert written_commands == ["echo registered-launch-marker"]


def test_handler_persists_shell_pid_and_reaps_stale_pid(
    terminal_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """The handler reaps a recorded stale pid before spawning and records the
    new spawn's shell pid on the task state."""
    stale_pid = 4_000_000  # nonexistent — reap must be a no-op but still clear it
    task_state = AgentTaskStateV2(workspace_id=WorkspaceID(), terminal_shell_pid=stale_pid)
    _set_task_state(terminal_task, task_state, services)

    shutdown_event = threading.Event()
    reaped: list[int] = []

    def fake_reap(pid: int) -> None:
        reaped.append(pid)

    terminal_id = make_agent_terminal_id(terminal_task.object_id)

    def watch_then_shutdown() -> None:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if get_terminal_manager(terminal_id) is not None:
                break
            time.sleep(0.05)
        shutdown_event.set()

    watcher = threading.Thread(target=watch_then_shutdown, daemon=True)
    watcher.start()
    with patch("sculptor.tasks.handlers.run_terminal_agent.v1.reap_stale_shell", side_effect=fake_reap):
        with pytest.raises(UserPausedTaskError):
            _run_terminal_agent_in_environment(
                task=terminal_task,
                task_state=task_state,
                project=project,
                underlying_env=environment,
                environment_concurrency_group=test_root_concurrency_group,
                services=services,
                settings=test_settings,
                shutdown_event=shutdown_event,
                on_started=None,
            )
    watcher.join(timeout=5.0)

    assert reaped == [stale_pid]
    # The new spawn's shell pid was recorded (and the stale one cleared first).
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(terminal_task.object_id)
    assert task_row is not None
    final_state = AgentTaskStateV2.model_validate(task_row.current_state)
    assert final_state.terminal_shell_pid is not None
    assert final_state.terminal_shell_pid != stale_pid
