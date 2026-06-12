"""Integration tests for click-to-pin tool pill popover semantics.

A click on a tool pill pins its popover open: hover-leave no longer closes
it. Clicking the same pinned pill again closes the popover. Pressing
Escape while pinned also closes it.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
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


@user_story("to keep a tool's details visible after clicking its pill")
def test_click_pins_popover_open(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a pill pins its popover; moving the cursor away does not close it."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARALLEL_READ_GREP_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_chat_view = get_alpha_chat_view(page)
    pill_row = alpha_chat_view.get_tool_pill_rows()
    expect(pill_row.first).to_be_visible()

    pills = pill_row.first.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)
    expect(pills).to_have_count(2)

    popover = alpha_chat_view.get_tool_pill_popover()

    # Click the Read pill to pin its popover open.
    pills.nth(0).click()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")

    # Move the cursor far away. A hover-opened popover would close after
    # CLOSE_DELAY_MS, but pinned popovers ignore hover-leave dismissal.
    page.mouse.move(0, 0)
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("pill_test_a.txt")


@user_story("to dismiss a pinned popover by clicking the same pill again")
def test_click_pinned_pill_again_closes(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a pinned pill a second time should close its popover."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARALLEL_READ_GREP_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_chat_view = get_alpha_chat_view(page)
    pill_row = alpha_chat_view.get_tool_pill_rows()
    expect(pill_row.first).to_be_visible()

    pills = pill_row.first.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)
    expect(pills).to_have_count(2)

    popover = alpha_chat_view.get_tool_pill_popover()

    # First click: pin open.
    pills.nth(0).click()
    expect(popover).to_be_visible()

    # Second click on the same pill: close.
    pills.nth(0).click()
    expect(popover).not_to_be_visible()


@user_story("to dismiss a pinned popover by pressing Escape")
def test_escape_closes_pinned_popover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Escape should close a pinned popover."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARALLEL_READ_GREP_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_chat_view = get_alpha_chat_view(page)
    pill_row = alpha_chat_view.get_tool_pill_rows()
    expect(pill_row.first).to_be_visible()

    pills = pill_row.first.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)
    expect(pills).to_have_count(2)

    popover = alpha_chat_view.get_tool_pill_popover()

    # Click to pin.
    pills.nth(0).click()
    expect(popover).to_be_visible()

    # Escape closes the pinned popover. Click takes focus to the pill, so
    # the keyboard handler on the toolbar will see the Escape key.
    page.keyboard.press("Escape")
    expect(popover).not_to_be_visible()
