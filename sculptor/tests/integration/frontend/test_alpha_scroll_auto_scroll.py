"""Integration tests for alpha chat auto-scroll and jump-to-bottom button."""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_jump_to_bottom_button
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _expect_jump_button_hidden(jump_btn: Locator, *, timeout: int = 5000) -> None:
    """Assert the jump button is in its hidden state (aria-hidden on wrapper).

    The button is always in the DOM (for focus-management), so we check the
    wrapper's aria-hidden attribute rather than Playwright's visibility check.
    """
    wrapper = jump_btn.page.get_by_test_id(ElementIDs.ALPHA_JUMP_TO_BOTTOM_WRAPPER)
    expect(wrapper).to_have_attribute("aria-hidden", "true", timeout=timeout)


def _wait_for_agent_idle_alpha(page: Page, *, timeout: int = 30000) -> None:
    """Wait for the agent to finish in alpha view by checking the StatusPill disappears."""
    status_pill = page.get_by_test_id(ElementIDs.STATUS_PILL)
    expect(status_pill).not_to_be_visible(timeout=timeout)


# Generate a long text response so the chat is scrollable
LONG_TEXT = "Lorem ipsum. " * 200

# Generate a very long streaming text: 5000 chars streamed in 50-char chunks
# with 0.1s delay = ~10 seconds of streaming
_STREAM_TEXT = "The quick brown fox jumps over the lazy dog. " * 112  # ~5040 chars


@user_story("to verify auto-scroll follows streaming and jump button appears when scrolled away")
def test_auto_scroll_and_jump_to_bottom(sculptor_instance_: SculptorInstance) -> None:
    """Test auto-scroll engagement/disengagement and jump-to-bottom button labels."""
    page = sculptor_instance_.page

    # Create a task with a long response
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()

    # Scroll to top — jump button should appear
    scroll_alpha_chat_to_top(page)
    page.wait_for_timeout(300)

    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible(timeout=5000)
    expect(jump_btn).to_contain_text("Jump")

    # Click jump button — should scroll to bottom and button should hide.
    # force=True: the virtualContent div inside the scroll container intercepts
    # Playwright's actionability check, but the button is clickable in real browsers.
    jump_btn.click(force=True)
    page.wait_for_timeout(500)
    _expect_jump_button_hidden(jump_btn)

    # Send a streaming message, then scroll away DURING the filling phase
    # (before pin-to-bottom) to check the "New activity" label.  Scroll-to-top-
    # on-send places the user message at the top and force-engages auto-scroll.
    # If we wait for pin-to-bottom, onReachBottom fires (acknowledging the
    # activity), so the label would be "Jump" instead of "New activity".
    # Scrolling away during filling keeps isAcknowledged false.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )

    # Wait very briefly for streaming to start (filling phase), then scroll
    # away before the response overflows and transitions to pin-to-bottom.
    # Must scroll before onReachBottom fires (which happens at pin-to-bottom).
    page.wait_for_timeout(500)
    scroll_alpha_chat_to_top(page)
    page.wait_for_timeout(300)

    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible(timeout=5000)
    expect(jump_btn).to_contain_text("New activity")

    # After streaming finishes, label should revert to "Jump"
    _wait_for_agent_idle_alpha(page)
    page.wait_for_timeout(500)
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible(timeout=5000)
    expect(jump_btn).to_contain_text("Jump")

    # Click "Jump" — scrolls to bottom
    jump_btn.click(force=True)
    page.wait_for_timeout(500)
    _expect_jump_button_hidden(jump_btn)


@user_story("to verify user can scroll away from bottom while agent is streaming (req 1.2)")
def test_user_can_scroll_during_streaming(sculptor_instance_: SculptorInstance) -> None:
    """Test that scrolling away during streaming disengages auto-scroll.

    Verifies observable behavior: scrolling away from the bottom while the agent
    is streaming should show the jump-to-bottom button (meaning auto-scroll
    disengaged) and keep it visible while streaming continues.
    """
    page = sculptor_instance_.page

    # Create a task with a long initial response so the chat is scrollable
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()

    # Send a streaming message — this emits text incrementally with real delays
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )

    # Wait for streaming to produce some content
    page.wait_for_timeout(2000)

    # Scroll to top while agent is actively streaming
    scroll_alpha_chat_to_top(page)

    # The jump-to-bottom button should appear, proving auto-scroll disengaged
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible(timeout=5000)

    # Button should still be visible after more streaming (auto-scroll stays disengaged)
    page.wait_for_timeout(1500)
    expect(jump_btn).to_be_visible()

    # Wait for the agent to finish before cleanup
    _wait_for_agent_idle_alpha(page)
