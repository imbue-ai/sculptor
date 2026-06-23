"""Unit tests for PiLoginService and broadcast_pi_models_refresh.

The interactive /login round-trip (pi actually writing auth.json) is covered by the
real_pi conformance tests; here we cover the service lifecycle (spawn registers a
PTY, teardown stops it and broadcasts) with a stand-in terminal manager, and the
broadcast's pi-only targeting.
"""

from unittest.mock import MagicMock

import pytest

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RefreshModelsUserMessage
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services import pi_login_service as pi_login_service_module
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction
from sculptor.services.pi_login_service import PiLoginMode
from sculptor.services.pi_login_service import PiLoginService
from sculptor.services.pi_login_service import broadcast_pi_models_refresh
from sculptor.services.pi_login_service import pi_login_terminal_id
from sculptor.services.task_service.api import TaskService
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)


def _make_agent_task(agent_config: PiAgentConfig | ClaudeCodeSDKAgentConfig) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=UserReference("anonymous"),
        organization_reference=OrganizationReference("anonymous"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(agent_config=agent_config, git_hash="x", system_prompt=None),
        current_state=AgentTaskStateV2(workspace_id=WorkspaceID()),
    )


def test_broadcast_pi_models_refresh_targets_only_pi_agents() -> None:
    pi_task = _make_agent_task(PiAgentConfig())
    claude_task = _make_agent_task(ClaudeCodeSDKAgentConfig())

    transaction = MagicMock(spec=TaskAndDataModelTransaction)
    transaction.get_active_tasks.return_value = (pi_task, claude_task)
    task_service = MagicMock()

    messaged_count = broadcast_pi_models_refresh(task_service, transaction)

    assert messaged_count == 1
    task_service.create_message.assert_called_once()
    call = task_service.create_message.call_args
    assert isinstance(call.kwargs["message"], RefreshModelsUserMessage)
    assert call.kwargs["task_id"] == pi_task.object_id


def test_broadcast_pi_models_refresh_no_pi_agents_messages_none() -> None:
    transaction = MagicMock(spec=TaskAndDataModelTransaction)
    transaction.get_active_tasks.return_value = (_make_agent_task(ClaudeCodeSDKAgentConfig()),)
    task_service = MagicMock()

    messaged_count = broadcast_pi_models_refresh(task_service, transaction)

    assert messaged_count == 0
    task_service.create_message.assert_not_called()


def test_spawn_registers_pty_and_teardown_stops_and_broadcasts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = MagicMock()
    monkeypatch.setattr(pi_login_service_module, "LocalTerminalManager", MagicMock(return_value=fake_manager))
    monkeypatch.setattr(pi_login_service_module, "write_launch_command", lambda *args, **kwargs: None)
    broadcast_mock = MagicMock()
    monkeypatch.setattr(pi_login_service_module, "broadcast_pi_models_refresh", broadcast_mock)

    service = PiLoginService(
        concurrency_group=MagicMock(spec=ConcurrencyGroup),
        data_model_service=MagicMock(spec=DataModelService),
        task_service=MagicMock(spec=TaskService),
    )

    login_id = service.spawn(PiLoginMode.LOGIN, "/fake/pi")
    terminal_id = pi_login_terminal_id(login_id)
    try:
        assert get_terminal_manager(terminal_id) is fake_manager
        assert service.is_active(login_id)
        fake_manager.start.assert_called_once()
    finally:
        service.teardown(login_id)

    assert get_terminal_manager(terminal_id) is None
    assert not service.is_active(login_id)
    fake_manager.stop.assert_called_once()
    broadcast_mock.assert_called_once()


def test_teardown_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = MagicMock()
    monkeypatch.setattr(pi_login_service_module, "LocalTerminalManager", MagicMock(return_value=fake_manager))
    monkeypatch.setattr(pi_login_service_module, "write_launch_command", lambda *args, **kwargs: None)
    broadcast_mock = MagicMock()
    monkeypatch.setattr(pi_login_service_module, "broadcast_pi_models_refresh", broadcast_mock)

    service = PiLoginService(
        concurrency_group=MagicMock(spec=ConcurrencyGroup),
        data_model_service=MagicMock(spec=DataModelService),
        task_service=MagicMock(spec=TaskService),
    )
    login_id = service.spawn(PiLoginMode.LOGOUT, "/fake/pi")

    service.teardown(login_id)
    service.teardown(login_id)  # second call must not raise or re-stop

    fake_manager.stop.assert_called_once()
    # Done and WebSocket-close both tear the same session down; only the call that
    # actually unregisters the PTY broadcasts, so the credential change fans out once.
    broadcast_mock.assert_called_once()
