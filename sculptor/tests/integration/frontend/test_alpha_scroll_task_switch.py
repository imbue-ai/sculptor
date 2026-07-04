"""Integration tests for alpha chat scroll position persistence across task switch."""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import navigate_to_workspace
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
        workspace_name="Scroll Task A",
    )
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    task_page_b = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task B response. {LONG_TEXT}"}}`',
        workspace_name="Scroll Task B",
    )
    chat_panel_b = task_page_b.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=2)

    # We're on task B.  Navigate to task A first. (Sidebar rows sort by name, so
    # navigate by name rather than position.)
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(2)
    navigate_to_workspace(page, "Scroll Task A")

    alpha_chat_view = get_alpha_chat_view(page)
    expect(alpha_chat_view).to_be_visible()

    # Switching to task A restores its saved scroll position (the bottom)
    # asynchronously.  Wait for the scroll machine to report it has settled
    # before scrolling — otherwise a late restore frame can clobber the
    # scroll-to-top below, which is the source of the CI flake.
    wait_for_alpha_scroll_settled(page)

    # Scroll to the top in task A and wait for scroll to settle
    scroll_alpha_chat_to_top(page)
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollTop < 10;
        }}"""
    )

    pos_a = get_alpha_scroll_position(page)

    # Switch to task B via its sidebar row (no reload). Both workspaces share the
    # ALPHA_CHAT_VIEW test id, so confirm task B's response text has mounted rather
    # than relying on visibility (already true while task A's view is still up) —
    # otherwise the switch may not have landed and the scroll-restore path is skipped.
    navigate_to_workspace(page, "Scroll Task B")
    expect(alpha_chat_view).to_contain_text("Task B response")

    # Navigate back to task A; confirm its chat remounted before checking scroll.
    navigate_to_workspace(page, "Scroll Task A")
    expect(alpha_chat_view).to_contain_text("Task A response")

    # Verify scroll position is restored (within 200px tolerance to account for
    # the virtualizer's dynamic paddingStart plus settling adjustments).
    page.wait_for_function(
        f"""(expectedPos) => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && Math.abs(el.scrollTop - expectedPos) < 200;
        }}""",
        arg=pos_a,
    )
