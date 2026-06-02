"""Tests for the harness registry's read-side resolver."""

from unittest.mock import MagicMock

from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.agents.data_types.ids import TaskID
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.harness_registry import create_agent_for_run
from sculptor.agents.harness_registry import get_harness_for_config
from sculptor.agents.hello_agent.harness import HELLO_HARNESS
from sculptor.agents.pi_agent.agent_wrapper import PiAgent
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.harness import AgentRunContext
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.api import WorkspaceService


def test_get_harness_for_config_resolves_claude() -> None:
    assert get_harness_for_config(ClaudeCodeSDKAgentConfig()) is CLAUDE_CODE_HARNESS


def test_get_harness_for_config_resolves_hello() -> None:
    assert get_harness_for_config(HelloAgentConfig()) is HELLO_HARNESS


def test_get_harness_for_config_resolves_pi() -> None:
    assert get_harness_for_config(PiAgentConfig()) is PI_HARNESS


def test_create_agent_for_run_constructs_pi_agent_with_pi_harness() -> None:
    project = Project(
        object_id=ProjectID(),
        organization_reference=OrganizationReference("org-1"),
        name="test",
    )
    context = AgentRunContext(
        task_data=AgentTaskInputsV2(agent_config=PiAgentConfig(), git_hash="deadbeef"),
        task_state=AgentTaskStateV2(workspace_id=WorkspaceID()),
        environment=MagicMock(spec=AgentExecutionEnvironment),
        project=project,
        task_id=TaskID(),
        workspace_service=MagicMock(spec=WorkspaceService),
    )
    agent = create_agent_for_run(context)
    assert isinstance(agent, PiAgent)
    assert agent.harness is PI_HARNESS
