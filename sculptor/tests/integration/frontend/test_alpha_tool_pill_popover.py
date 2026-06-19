"""Integration test for tool pill popover targeting.

Each tool in a tool group renders as its own pill. Clicking a pill opens a
popover with that tool's details. Clicking a different pill switches the
popover to the other tool.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to view individual tool details by clicking each tool name in a group")
def test_tool_pill_popover_switches_on_different_pill_click(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a pill opens a popover scoped to that one tool; other pills swap to their own popover."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Read", "tool_input": {"file_path": "/tmp/pill_test_a.txt"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "hello_pill_test", "path": "/tmp"}}
    ]}},
    {"command": "text", "args": {"text": "Done with both tools."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Two individual pills (Read + Grep) should render in a single toolbar row.
    pill_rows = chat_panel.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = chat_panel.get_tool_pills()
    expect(pills).to_have_count(2)

    # Click the first pill (Read) — its popover should show the file path.
    # (For single-entry pills the popover shows the per-tool details directly,
    # with no tool-name header.)
    pills.nth(0).click()
    popover = chat_panel.get_tool_pill_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")

    # Click the second pill (Grep) — popover swaps to Grep's pattern.
    pills.nth(1).click()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("hello_pill_test")
