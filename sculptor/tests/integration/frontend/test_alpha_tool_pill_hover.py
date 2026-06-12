"""Integration tests for hover-triggered tool pill popovers.

Hovering a tool pill opens its popover after a short delay. Mouse-leave
closes after a shorter delay. Sliding the cursor from one pill to a sibling
swaps the popover content without closing in between (the popover element
stays mounted; only its content changes).
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_PARALLEL_READ_GREP_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Read", "tool_input": {"file_path": "/tmp/pill_test_a.txt"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "hello_pill_test", "path": "/tmp"}}
    ]}},
    {"command": "text", "args": {"text": "Done with both tools."}}
  ]
}`"""


@user_story("to peek at a tool's details just by hovering its pill")
def test_hover_opens_pill_popover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Hovering a tool pill should open its popover after the open delay."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARALLEL_READ_GREP_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)

    popover = alpha_view.get_tool_pill_popover()
    expect(popover).not_to_be_visible()

    # Hover the Read pill — popover should open after the ~600ms delay.
    pills.nth(0).hover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")


@user_story("to dismiss a hover-opened popover by moving the cursor away")
def test_hover_leave_closes_popover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Moving the cursor off the pill row should close a hover-opened popover."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARALLEL_READ_GREP_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)

    popover = alpha_view.get_tool_pill_popover()

    # Open via hover.
    pills.nth(0).hover()
    expect(popover).to_be_visible()

    # Move the cursor far away from the pill row and the popover. The
    # close timer (CLOSE_DELAY_MS = 80ms) should fire and dismiss it.
    page.mouse.move(0, 0)
    expect(popover).not_to_be_visible()


@user_story("to compare sibling tools by sliding the cursor across pills")
def test_hover_sibling_swaps_popover_content(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Hovering pill A then pill B should swap popover content without unmounting."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARALLEL_READ_GREP_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows.first).to_be_visible()

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)

    popover = alpha_view.get_tool_pill_popover()

    # Hover the Read pill — popover shows the Read file path.
    pills.nth(0).hover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")

    # Slide to the Grep pill — popover swaps to Grep's pattern. The
    # adjacent hover zones make this an instant switch (no re-open delay).
    pills.nth(1).hover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("hello_pill_test")
    expect(popover).not_to_contain_text("pill_test_a.txt")
