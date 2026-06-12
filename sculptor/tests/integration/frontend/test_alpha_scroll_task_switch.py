"""Integration tests for alpha chat scroll position persistence across task switch."""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

LONG_TEXT = "Lorem ipsum dolor sit amet. " * 150


@user_story("to have scroll position preserved when switching between tasks")
def test_scroll_position_restored_on_task_switch(sculptor_instance_: SculptorInstance) -> None:
    """Test that scroll position is saved and restored when switching tasks."""
    page = sculptor_instance_.page

    # Create both tasks and wait for their messages to complete.
    task_page_a = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task A response. {LONG_TEXT}"}}`',
    )
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    task_page_b = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task B response. {LONG_TEXT}"}}`',
    )
    chat_panel_b = task_page_b.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=2)

    # We're on task B.  Navigate to task A first.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)
    workspace_tabs.first.click()
    page.wait_for_timeout(500)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()

    # Scroll to the top in task A
    scroll_alpha_chat_to_top(page)
    page.wait_for_timeout(300)

    # Record position
    pos_a = get_alpha_scroll_position(page)

    # Switch to task B via workspace tab (no reload)
    workspace_tabs.last.click()
    page.wait_for_timeout(500)

    # Navigate back to task A
    workspace_tabs.first.click()
    page.wait_for_timeout(1000)

    # Verify scroll position is restored (should be near the top where we left it)
    restored_pos = get_alpha_scroll_position(page)
    # Allow tolerance of 200px to account for the virtualizer's dynamic paddingStart
    # (sized to the intro block, typically ~154px) plus settling adjustments.
    assert abs(restored_pos - pos_a) < 200, f"Expected scroll position ~{pos_a}, got {restored_pos}"
