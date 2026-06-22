"""Tests for broadcast_pi_models_refresh: the fan-out that tells running pi agents
to re-read credentials after a global change, targeting pi agents only.
"""

from unittest.mock import MagicMock

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RefreshModelsUserMessage
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction
from sculptor.web.app import broadcast_pi_models_refresh


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
    services = MagicMock()

    messaged_count = broadcast_pi_models_refresh(services, transaction)

    assert messaged_count == 1
    services.task_service.create_message.assert_called_once()
    call = services.task_service.create_message.call_args
    assert isinstance(call.kwargs["message"], RefreshModelsUserMessage)
    assert call.kwargs["task_id"] == pi_task.object_id


def test_broadcast_pi_models_refresh_no_pi_agents_messages_none() -> None:
    transaction = MagicMock(spec=TaskAndDataModelTransaction)
    transaction.get_active_tasks.return_value = (_make_agent_task(ClaudeCodeSDKAgentConfig()),)
    services = MagicMock()

    messaged_count = broadcast_pi_models_refresh(services, transaction)

    assert messaged_count == 0
    services.task_service.create_message.assert_not_called()
