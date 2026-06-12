"""Integration tests for alpha chat scroll behaviors.

Covers:
- Scroll-to-top: first message padding is visible when scrolled to top
- Jump-to-bottom button: appears when scrolled away, clicking it scrolls to bottom
- Scroll position not off after agent tab round-trip
- Last user message stays visible at maximum scroll after agent tab switch
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_container_height
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import get_intro_bottom_offset
from sculptor.testing.elements.alpha_chat_view import get_message_top_offset
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import close_bottom_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_LONG_TEXT = " ".join(["This is a longer response that should take up some space."] * 20)
_SHORT_TEXT = "Short reply."


def _wait_for_agent_idle(page: Page, *, timeout: int = 30000) -> None:
    """Wait for the agent to finish by checking the StatusPill disappears."""
    status_pill = page.get_by_test_id(ElementIDs.STATUS_PILL)
    expect(status_pill).not_to_be_visible(timeout=timeout)


@user_story("to see the first message without extra padding above it when scrolled to top")
def test_first_message_visible_at_top(sculptor_instance_: SculptorInstance) -> None:
    """When scrolled to the top, the first message should be visible
    with consistent padding (paddingStart), not pushed off-screen.

    This tests the fix for scroll-to-top setting scrollTop=0 for the
    first message to keep paddingStart visible.
    """
    page = sculptor_instance_.page

    # Create a conversation with enough content to enable scrolling
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up to generate more content
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    _wait_for_agent_idle(page)
    page.wait_for_timeout(500)

    # Scroll to top
    scroll_alpha_chat_to_top(page)
    page.wait_for_timeout(500)

    # The first message (data-index=0) should be visible within the viewport
    first_msg_offset = get_message_top_offset(page, data_index=0)
    container_height = get_alpha_container_height(page)

    assert first_msg_offset >= 0, (
        f"First message is above viewport (offset={first_msg_offset:.0f}px). paddingStart may not be preserved."
    )
    assert first_msg_offset < container_height, (
        f"First message is below viewport (offset={first_msg_offset:.0f}px, viewport={container_height:.0f}px)."
    )

    # The first message should be at or just below the intro text block.
    # paddingStart is dynamic (= intro block height), so we measure the
    # intro bottom and verify the first message starts near it.
    intro_bottom = get_intro_bottom_offset(page)
    assert first_msg_offset >= intro_bottom - 5, (
        f"First message (offset={first_msg_offset:.0f}px) is above the intro block (bottom={intro_bottom:.0f}px)."
    )
    assert first_msg_offset < intro_bottom + 50, (
        f"First message (offset={first_msg_offset:.0f}px) is too far below the intro block (bottom={intro_bottom:.0f}px)."
    )


@user_story("to see the jump button when scrolled away and dismiss it by clicking")
def test_jump_button_appears_and_works(sculptor_instance_: SculptorInstance) -> None:
    """Scrolling away from the bottom should show the jump-to-bottom button.
    Clicking it should scroll to bottom and hide the button.
    """
    page = sculptor_instance_.page

    # Create a conversation with enough content to enable scrolling
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Add more content
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    _wait_for_agent_idle(page)
    page.wait_for_timeout(1000)

    jump_button = page.get_by_test_id(ElementIDs.ALPHA_JUMP_TO_BOTTOM_BUTTON)

    # Scroll to top — jump button should appear
    scroll_alpha_chat_to_top(page)
    page.wait_for_timeout(500)

    expect(jump_button).to_be_visible(timeout=5000)

    # Record scroll position before clicking
    scroll_before_click = get_alpha_scroll_position(page)

    # Click the jump button — should scroll toward the bottom
    jump_button.click()
    page.wait_for_timeout(500)

    scroll_after_click = get_alpha_scroll_position(page)
    assert scroll_after_click > scroll_before_click, (
        f"Jump button didn't scroll down: before={scroll_before_click:.0f}px, after={scroll_after_click:.0f}px"
    )


@user_story("to have the first message remain visible at top after an agent tab round-trip")
def test_first_message_visible_after_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """After scrolling to top, switching to another agent, and switching back,
    the first message should still be visible in the viewport.  This tests
    that scroll persistence restores the scroll position near the top.
    """
    page = sculptor_instance_.page

    # Create agent 1 with enough content to scroll
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Add agent 2
    add_agent_button = page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)
    add_agent_button.click()
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)

    # Navigate to agent 1
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)
    agent_tabs.first.click()
    page.wait_for_timeout(500)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    _wait_for_agent_idle(page)
    page.wait_for_timeout(500)

    # Scroll to top
    scroll_alpha_chat_to_top(page)
    page.wait_for_timeout(500)

    # Verify first message is visible before switch
    msg0_before = get_message_top_offset(page, data_index=0)
    container_height = get_alpha_container_height(page)
    assert msg0_before >= 0 and msg0_before < container_height, "Message 0 should be visible at top"

    # Switch to agent 2
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.last.click()
    page.wait_for_timeout(500)

    # Switch back to agent 1
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.first.click()
    page.wait_for_timeout(1000)

    # The first message should still be visible in the viewport.
    # The scroll persistence restores by message ID, so the exact pixel
    # position may differ slightly, but the message should be on-screen.
    msg0_after = get_message_top_offset(page, data_index=0)
    container_height_after = get_alpha_container_height(page)

    assert msg0_after >= -20, (
        f"First message scrolled off-screen after agent switch (offset={msg0_after:.0f}px). Scroll persistence failed to restore near the top."
    )
    assert msg0_after < container_height_after, (
        f"First message not in viewport after agent switch (offset={msg0_after:.0f}px, viewport={container_height_after:.0f}px)."
    )


@user_story("to have the last user message remain visible at max scroll after agent tab switch")
def test_user_message_visible_at_max_scroll_after_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """After switching agents and back, scrolling to the maximum position
    should still keep the last user message visible.  This is a complement
    to test_dynamic_padding_survives_agent_switch — testing that the
    dynamic paddingEnd constrains scroll range correctly.
    """
    page = sculptor_instance_.page

    # Create agent 1 with a short conversation
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()

    # Close the bottom panel to maximize chat height for scroll tests.
    # Must be done after workspace creation since the terminal only exists in workspaces.
    close_bottom_panel(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Add agent 2
    add_agent_button = page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)
    add_agent_button.click()
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)

    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)
    agent_tabs.first.click()
    page.wait_for_timeout(500)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    _wait_for_agent_idle(page)
    page.wait_for_timeout(500)

    # Switch to agent 2 and back
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.last.click()
    page.wait_for_timeout(500)

    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    agent_tabs.first.click()
    page.wait_for_timeout(1000)

    # Scroll down maximally
    scroll_alpha_chat_by(page, 10000)
    page.wait_for_timeout(500)

    # The last user message (data-index=2) should still be visible
    user_msg_offset = get_message_top_offset(page, data_index=2)
    container_height = get_alpha_container_height(page)

    assert user_msg_offset >= 0, (
        f"User message scrolled off-screen after agent switch (offset={user_msg_offset:.0f}px). Dynamic paddingEnd likely reset."
    )
    assert user_msg_offset < container_height, (
        f"User message not in viewport (offset={user_msg_offset:.0f}px, viewport={container_height:.0f}px)."
    )
