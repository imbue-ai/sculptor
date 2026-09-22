"""The product default model a Claude agent reports, and its streaming support."""

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.state.messages import LLMModel
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import create_initial_task_view


def _make_view_without_a_selected_model() -> CodingAgentTaskView:
    """A Claude agent that carries no creation-time model and no chat selection."""
    task = Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(
            agent_config=ClaudeCodeSDKAgentConfig(),
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


def test_unselected_model_falls_back_to_the_pinned_1m_opus() -> None:
    assert _make_view_without_a_selected_model().model == LLMModel.CLAUDE_5_5_OPUS


def test_the_default_model_supports_smooth_streaming() -> None:
    """Smooth streaming is opt-in per model, so the default has to be on the list.

    Leaving the default off it degrades every new agent to unstreamed responses
    without failing anything else.
    """
    assert _make_view_without_a_selected_model().is_smooth_streaming_supported
