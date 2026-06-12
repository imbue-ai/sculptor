"""Tests for the workspace-harness → agent-config router in web/app.py.

Agent-config selection is coupled to the workspace's persisted `harness`
value. The helper here is the single place every task-creation route
consults, so a direct unit test covers all sites at once.
"""

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.app import _agent_config_for_workspace


def _make_workspace(harness: HarnessName) -> Workspace:
    return Workspace(
        object_id=WorkspaceID(),
        project_id=ProjectID(),
        organization_reference=OrganizationReference("org-1"),
        description="ws",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        harness=harness,
    )


def test_agent_config_for_workspace_picks_pi_when_harness_is_pi() -> None:
    assert isinstance(_agent_config_for_workspace(_make_workspace(HarnessName.PI)), PiAgentConfig)


def test_agent_config_for_workspace_picks_claude_when_harness_is_claude() -> None:
    assert isinstance(_agent_config_for_workspace(_make_workspace(HarnessName.CLAUDE)), ClaudeCodeSDKAgentConfig)
