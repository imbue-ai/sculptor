"""Integration tests for Task Page - Tool Results display.

Tests that tool results (TaskCreate, Bash) are correctly displayed
in the chat panel during and after streaming responses.

This is a regression test for SCU-63 where tool results were being dropped
during streaming because ResponseBlockAgentMessage containing ToolResultBlock
was skipped when is_streaming_active was True.

Note: We avoid tools that use absolute file paths (Read, Write, Edit) because
the agent returns paths containing temp directory names. These paths get cached
in snapshots and fail to match on replay when a different temp directory is used.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see tool results displayed after streaming completes")
def test_tool_results_displayed_after_streaming(sculptor_instance_: SculptorInstance) -> None:
    """Test that tool results are visible in the chat after streaming completes.

    This test triggers both sequential and concurrent tool calls:
    - Sequential tools (TaskCreate, then Bash) render as their own pill rows.
    - Concurrent tools (multiple Bash in parallel) collapse into a single pill row.

    Verifies:
    1. Tool calls are visible after streaming completes.
    2. All six tool invocations render (2 TaskCreate + 1 Bash + 3 parallel Bash).
    3. The parallel-Bash row contains exactly three Bash pills.

    Regression test for SCU-63 (tool results dropped during streaming) and
    SCU-149 (orphaned in-progress tool calls duplicating with their result).
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "First task", "status": "pending", "activeForm": "Working on first task"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Second task", "status": "pending", "activeForm": "Working on second task"}},
    {"command": "text", "args": {"text": "step 1 is complete"}},
    {"command": "bash", "args": {"command": "echo step2"}},
    {"command": "text", "args": {"text": "step 2 is complete"}},
    {
      "command": "parallel_tools",
      "args": {
        "tools": [
          {"tool_name": "Bash", "tool_input": {"command": "echo parallel1"}},
          {"tool_name": "Bash", "tool_input": {"command": "echo parallel2"}},
          {"tool_name": "Bash", "tool_input": {"command": "echo parallel3"}}
        ]
      }
    },
    {"command": "text", "args": {"text": "all steps are complete"}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )

    chat_panel = task_page.get_chat_panel()

    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_panel.get_messages().first).to_be_visible()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)

    # Bash tool calls render as ALPHA_CHAT_BASH_BLOCK pills; non-Bash tools
    # (TaskCreate) render as ALPHA_CHAT_TOOL_PILL. Together the four Bash
    # invocations plus the two TaskCreates must all render — if any tool
    # result were dropped (SCU-63) the count would be lower; if a ToolUseBlock
    # and its ToolResultBlock both rendered (SCU-149) the count would be higher.
    bash_pills = chat_panel.get_bash_blocks()
    expect(bash_pills).to_have_count(4)

    tool_pills = chat_panel.get_tool_pills()
    expect(tool_pills).to_have_count(2)

    # SCU-149 catch-all: no rendered tool surface may be stuck in the
    # ``initializing`` state once streaming has finished. A count check alone
    # would miss the "stuck initializing" symptom — the counts would still
    # match while the row visibly reads "Running …". Asserting zero
    # in-progress rows across all alpha tool surfaces locks in the behavior
    # the original SCU-149 regression test covered.
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)

    # The three parallel Bash calls collapse into a single pill row.
    pill_rows = chat_panel.get_tool_pill_rows()
    parallel_row = pill_rows.last
    expect(parallel_row.get_by_test_id(ElementIDs.ALPHA_CHAT_BASH_BLOCK)).to_have_count(3)
