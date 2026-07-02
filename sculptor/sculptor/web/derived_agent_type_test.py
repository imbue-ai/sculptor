"""Tests for CodingAgentTaskView.agent_type / registration_id.

Both are derived from the persisted `agent_config` subtype on the task's
input_data, so the frontend can tell which harness owns a transcript.
"""

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.agent import AgentConfigTypes
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.data_types import AgentTypeName
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import create_initial_task_view


def _make_task_view(agent_config: AgentConfigTypes) -> CodingAgentTaskView:
    task = Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(
            agent_config=agent_config,
            git_hash="abc123",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=WorkspaceID()),
        outcome=TaskState.RUNNING,
    )
    view = create_initial_task_view(task, SculptorSettings())
    assert isinstance(view, CodingAgentTaskView)
    view.update_task(task)
    return view


def _registered_config() -> RegisteredTerminalAgentConfig:
    return RegisteredTerminalAgentConfig(
        registration_id="my-tool",
        display_name="My Tool",
        launch_command="my-tool",
    )


def test_claude_agent_type() -> None:
    view = _make_task_view(ClaudeCodeSDKAgentConfig())
    assert view.agent_type == AgentTypeName.CLAUDE
    assert view.registration_id is None


def test_pi_agent_type() -> None:
    view = _make_task_view(PiAgentConfig())
    assert view.agent_type == AgentTypeName.PI
    assert view.registration_id is None


def test_terminal_agent_type() -> None:
    view = _make_task_view(TerminalAgentConfig())
    assert view.agent_type == AgentTypeName.TERMINAL
    assert view.registration_id is None


def test_registered_agent_type_carries_registration_id() -> None:
    view = _make_task_view(_registered_config())
    assert view.agent_type == AgentTypeName.REGISTERED
    assert view.registration_id == "my-tool"


def test_hello_config_has_no_agent_type() -> None:
    # The internal hello harness maps to no user-facing agent type, so the view
    # reports null rather than guessing.
    view = _make_task_view(HelloAgentConfig())
    assert view.agent_type is None
    assert view.registration_id is None


def test_agent_type_and_registration_id_serialize_on_the_view() -> None:
    # The frontend reads these off the serialized CodingAgentTaskView, so the
    # computed fields must appear in the dumped payload.
    dumped = _make_task_view(_registered_config()).model_dump(by_alias=True)
    assert dumped["agentType"] == AgentTypeName.REGISTERED
    assert dumped["registrationId"] == "my-tool"
