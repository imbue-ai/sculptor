"""Integration tests for tool pill keyboard navigation.

Covers the intra-row arrow-key flows in AlphaToolPillRow.tsx:

- Left/Right with a popover open: moves the popover (and focus) to the
  prev/next pill within a row.
- Enter on a focused pill: pins the popover open.
- Escape: closes the popover.

Cross-row Up/Down navigation is exercised at the unit level in
ToolNavigationContext.test.tsx; rendering it through a multi-message
integration scenario is brittle because each AlphaToolGroup wraps its
tools in its own provider scope, so cross-message Up/Down does not flow.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to flip the open tool popover between sibling pills with the arrow keys")
def test_arrow_keys_move_open_popover_within_row(
    sculptor_instance_: SculptorInstance,
) -> None:
    """ArrowRight / ArrowLeft swap the open popover to the next/prev pill in the same row."""
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

    alpha_view = get_alpha_chat_view(page)
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)

    # Click the first pill (Read) — popover pins open with the file path.
    pills.nth(0).click()
    popover = alpha_view.get_tool_pill_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")

    # ArrowRight — popover content swaps to the Grep pill.
    page.keyboard.press("ArrowRight")
    expect(popover).to_contain_text("hello_pill_test")
    expect(popover).not_to_contain_text("pill_test_a.txt")

    # ArrowLeft — popover swings back to the Read pill.
    page.keyboard.press("ArrowLeft")
    expect(popover).to_contain_text("pill_test_a.txt")
    expect(popover).not_to_contain_text("hello_pill_test")


@user_story("to dismiss an open tool popover by pressing Escape")
def test_escape_closes_popover_and_restores_focus(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Escape closes a pinned popover; it disappears from the DOM."""
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
    {"command": "text", "args": {"text": "Done."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)

    pills.nth(0).click()
    popover = alpha_view.get_tool_pill_popover()
    expect(popover).to_be_visible()

    page.keyboard.press("Escape")
    # The popover testid div is conditionally rendered on `openPill`, so
    # closing it removes it from the DOM (count drops to 0). `to_be_hidden`
    # handles either case (hidden or removed).
    expect(popover).to_be_hidden()


@user_story("to open a tool popover by pressing Enter on a focused pill")
def test_enter_on_focused_pill_opens_popover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Focusing a pill and pressing Enter pins the popover open; Escape closes it."""
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
    {"command": "text", "args": {"text": "Done."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)

    # Focus the first pill directly. Tab-from-anywhere is brittle (relies on
    # natural tab order through the whole chat surface), so anchor focus on
    # the pill itself and exercise just the key handler.
    pills.nth(0).focus()

    page.keyboard.press("Enter")
    popover = alpha_view.get_tool_pill_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")

    page.keyboard.press("Escape")
    expect(popover).to_be_hidden()
