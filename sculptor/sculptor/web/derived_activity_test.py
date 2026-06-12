"""Tests for CodingAgentTaskView.current_activity and last_activity."""

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.ids import AssistantMessageID
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.chat_state import ToolUseBlock
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import create_initial_task_view


def _make_task_view() -> CodingAgentTaskView:
    workspace_id = WorkspaceID()
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
        current_state=AgentTaskStateV2(workspace_id=workspace_id),
        outcome=TaskState.RUNNING,
    )
    settings = SculptorSettings()
    view = create_initial_task_view(task, settings)
    assert isinstance(view, CodingAgentTaskView)
    view.update_task(task)
    return view


def _tool_use_message(tool_name: str, tool_input: dict[str, object] | None = None) -> ResponseBlockAgentMessage:
    return ResponseBlockAgentMessage.model_construct(
        message_id=AgentMessageID(),
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-1"),
        content=(ToolUseBlock.model_construct(id="tool-1", name=tool_name, input=tool_input or {}),),
    )


def _text_message(text: str) -> ResponseBlockAgentMessage:
    return ResponseBlockAgentMessage.model_construct(
        message_id=AgentMessageID(),
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-1"),
        content=(TextBlock.model_construct(text=text),),
    )


def test_no_messages_returns_none() -> None:
    view = _make_task_view()
    assert view.current_activity is None
    assert view.last_activity is None


def test_tool_use_returns_tool_description() -> None:
    view = _make_task_view()
    view.add_message(_tool_use_message("Edit", {"file_path": "/foo/bar.py"}))

    assert view.current_activity == "Editing bar.py"
    assert view.last_activity == "Edited bar.py"


def test_text_after_tool_use_returns_responding() -> None:
    """When the agent writes text after a tool call, activity should show 'Responding'."""
    view = _make_task_view()
    view.add_message(_tool_use_message("Bash"))
    view.add_message(_text_message("Here are the results of the test run."))

    assert view.current_activity == "Responding"
    assert view.last_activity == "Responded"


def test_tool_use_after_text_returns_tool_description() -> None:
    """When the agent makes a tool call after writing text, activity should show the tool call."""
    view = _make_task_view()
    view.add_message(_text_message("Let me check the file."))
    view.add_message(_tool_use_message("Read", {"file_path": "/src/main.py"}))

    assert view.current_activity == "Reading main.py"
    assert view.last_activity == "Read main.py"


def test_whitespace_only_text_is_ignored() -> None:
    """Empty or whitespace-only text blocks should be skipped."""
    view = _make_task_view()
    view.add_message(_tool_use_message("Grep"))
    view.add_message(_text_message("   "))

    assert view.current_activity == "Searching codebase"
    assert view.last_activity == "Searched codebase"


def test_mixed_content_block_text_after_tool() -> None:
    """When a single message has a tool call followed by text, the last block (text) wins."""
    view = _make_task_view()
    view.add_message(
        ResponseBlockAgentMessage.model_construct(
            message_id=AgentMessageID(),
            role="assistant",
            assistant_message_id=AssistantMessageID("assistant-1"),
            content=(
                ToolUseBlock.model_construct(id="tool-1", name="Bash", input={}),
                TextBlock.model_construct(text="Done running the command."),
            ),
        )
    )

    assert view.current_activity == "Responding"
    assert view.last_activity == "Responded"
