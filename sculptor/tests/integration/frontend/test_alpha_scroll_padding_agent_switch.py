"""Integration test for dynamic bottom padding surviving agent tab switches.

When a user sends a message and the agent responds with a short reply, the
dynamic paddingEnd ensures the last user message can be scrolled to the top
of the viewport.  This padding must survive switching to a different agent
tab and back.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_container_height
from sculptor.testing.elements.alpha_chat_view import get_message_top_offset
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import close_bottom_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_SHORT_TEXT = "Hello, this is a short reply."


def _wait_for_agent_idle_alpha(page: Page, *, timeout: int = 30000) -> None:
    """Wait for the agent to finish by checking the StatusPill disappears."""
    status_pill = page.get_by_test_id(ElementIDs.STATUS_PILL)
    expect(status_pill).not_to_be_visible(timeout=timeout)


@user_story("to have dynamic bottom padding survive agent tab switches")
def test_dynamic_padding_survives_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """Dynamic paddingEnd should persist after switching to another agent and back.

    Steps:
    1. Create agent 1 with a short conversation (user + assistant + user + assistant)
    2. Add agent 2 to the workspace
    3. Navigate to agent 1 and verify dynamic padding constrains scroll
    4. Navigate to agent 2
    5. Navigate back to agent 1
    6. Verify dynamic padding still constrains scroll (user message visible)
    """
    page = sculptor_instance_.page

    # --- Setup: create agent 1 with two exchanges in classic view ---
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Close the bottom panel to maximize chat height for scroll tests.
    # Must be done after workspace creation since the terminal only exists in workspaces.
    close_bottom_panel(page)

    # Send a follow-up so we have a "last user message" at data-index=2
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # --- Add agent 2 to the same workspace ---
    add_agent_button = page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)
    add_agent_button.click()
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)

    # Navigate to agent 1 to verify baseline padding.
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)
    agent_tabs.first.click()
    page.wait_for_timeout(500)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()

    # Wait for agent 1 to be idle and measurements to settle
    _wait_for_agent_idle_alpha(page)
    page.wait_for_timeout(500)

    # Baseline check: scroll down maximally — user message at index 2 should
    # remain visible thanks to dynamic paddingEnd.
    scroll_alpha_chat_by(page, 10000)
    page.wait_for_timeout(500)

    user_msg_offset = get_message_top_offset(page, data_index=2)
    container_height = get_alpha_container_height(page)

    assert user_msg_offset >= 0, f"Baseline: user message scrolled off-screen (offset={user_msg_offset:.0f}px)."
    assert user_msg_offset < container_height, (
        f"Baseline: user message not in viewport (offset={user_msg_offset:.0f}px, viewport={container_height:.0f}px)."
    )

    # --- Switch to agent 2 ---
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.last.click()
    page.wait_for_timeout(500)

    # --- Switch back to agent 1 ---
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.first.click()
    page.wait_for_timeout(1000)

    # Scroll down maximally — user message at index 2 should STILL be visible.
    # This is the crux of the bug: without the fix, dynamic paddingEnd resets
    # to the static fallback (64px), allowing the user message to scroll off.
    scroll_alpha_chat_by(page, 10000)
    page.wait_for_timeout(500)

    user_msg_offset_after = get_message_top_offset(page, data_index=2)
    container_height_after = get_alpha_container_height(page)

    assert user_msg_offset_after >= 0, (
        f"After agent switch: user message scrolled off-screen (offset={user_msg_offset_after:.0f}px). Dynamic paddingEnd likely reset to static fallback."
    )
    assert user_msg_offset_after < container_height_after, (
        f"After agent switch: user message not in viewport (offset={user_msg_offset_after:.0f}px, viewport={container_height_after:.0f}px)."
    )


@user_story("to have stable scroll height after switching agent tabs")
def test_scroll_height_settles_after_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """After switching agent tabs and back, the scrollHeight should settle to the
    same value it had before the switch.  This verifies that dynamic padding
    recalculation doesn't permanently change the virtual layout.
    """
    page = sculptor_instance_.page

    # --- Setup: create agent 1 with two exchanges in classic view ---
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # --- Add agent 2 ---
    add_agent_button = page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)
    add_agent_button.click()
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)

    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)
    agent_tabs.first.click()
    page.wait_for_timeout(500)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    _wait_for_agent_idle_alpha(page)
    page.wait_for_timeout(500)

    # Record the scrollHeight BEFORE switching.
    alpha_view = page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)
    before_scroll_height = alpha_view.evaluate("el => el.scrollHeight")
    assert before_scroll_height > 0

    # --- Switch to agent 2 ---
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.last.click()
    page.wait_for_timeout(500)

    # --- Switch back to agent 1 ---
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.first.click()
    page.wait_for_timeout(1000)

    # The scrollHeight should settle to the same value as before the switch.
    alpha_view = page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)
    after_scroll_height = alpha_view.evaluate("el => el.scrollHeight")

    assert after_scroll_height == before_scroll_height, (
        f"scrollHeight changed from {before_scroll_height} to {after_scroll_height} after agent switch round-trip."
    )
