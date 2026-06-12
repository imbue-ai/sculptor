"""Integration tests for scroll-to-top on user message send."""

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_alpha_container_height
from sculptor.testing.elements.alpha_chat_view import get_jump_to_bottom_button
from sculptor.testing.elements.alpha_chat_view import get_jump_to_bottom_wrapper
from sculptor.testing.elements.alpha_chat_view import get_message_top_offset
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import close_bottom_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Short initial text so the first response finishes quickly
_SHORT_TEXT = "Hello, this is a short reply."

# Long streaming text to trigger overflow and pin-to-bottom transition
_LONG_STREAM_TEXT = "The quick brown fox jumps over the lazy dog. " * 112  # ~5040 chars


def _expect_jump_button_hidden(jump_btn: Locator) -> None:
    """Assert the jump button is in its hidden state (aria-hidden on wrapper).

    The button is always in the DOM (for focus-management), so we check the
    wrapper's aria-hidden attribute rather than Playwright's visibility check.
    """
    wrapper = get_jump_to_bottom_wrapper(jump_btn.page)
    expect(wrapper).to_have_attribute("aria-hidden", "true")


def _wait_for_agent_idle_alpha(chat_panel, *, timeout: int = 30000) -> None:
    """Wait for the agent to finish by checking the thinking indicator disappears."""
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=timeout)


@user_story("to verify user message scrolls to the top of the viewport on send")
def test_scroll_to_top_on_send(sculptor_instance_: SculptorInstance) -> None:
    """When a user sends a message, it should scroll to the top of the viewport."""
    page = sculptor_instance_.page

    # Create a task with an initial response
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a streaming message and verify the user message is scrolled to the
    # upper portion of the viewport (scroll-to-top behavior). The exact offset
    # depends on timing and virtualizer corrections, so we verify the message
    # appears in the top half of the viewport rather than at the bottom.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_LONG_STREAM_TEXT}", "chunk_size": 100, "delay_seconds": 0.05}}`',
    )

    # Poll for the user message (data-index=2) to appear in the top half of
    # the viewport. With scroll-to-top, the message should be near the top.
    # Without it, the message would be near the bottom (pin-to-bottom default).
    try:
        page.wait_for_function(
            f"""() => {{
                const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
                const item = container && container.querySelector('[data-index="2"]');
                if (!container || !item) return false;
                const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
                const halfHeight = container.clientHeight / 2;
                return offset >= 0 && offset < halfHeight;
            }}""",
        )
    except Exception:
        diag = get_message_top_offset(page, data_index=2)
        container_h = get_alpha_container_height(page)
        raise AssertionError(
            f"User message not in upper half after scroll-to-top. offset={diag:.0f} containerH={container_h:.0f}"
        )

    # Wait for agent to finish before cleanup
    _wait_for_agent_idle_alpha(chat_panel, timeout=60000)


@user_story("to verify response fills below user message then transitions to pin-to-bottom")
def test_filling_to_pin_transition(sculptor_instance_: SculptorInstance) -> None:
    """Response should fill below the user message, then pin-to-bottom when it overflows."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a streaming message with a long response
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_LONG_STREAM_TEXT}", "chunk_size": 100, "delay_seconds": 0.05}}`',
    )

    # Wait for streaming to complete and agent to become idle
    _wait_for_agent_idle_alpha(chat_panel, timeout=60000)

    # After streaming completes with a long response, auto-scroll should have
    # transitioned to pin-to-bottom.  The jump button should be hidden (at bottom).
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)


@user_story("to verify jump-to-bottom button is suppressed between send and response arrival")
def test_jump_button_suppressed_on_send(sculptor_instance_: SculptorInstance) -> None:
    """Jump-to-bottom button should not appear between message send and streaming start."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Close the bottom panel (terminal) so chat height is maximised; with the
    # terminal open the short conversation can still exceed the viewport and
    # the jump button surfaces after the response arrives, flipping the
    # final "still hidden" assertion below.
    close_bottom_panel(page)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a message — the jump button should be suppressed immediately after
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )

    # Check immediately — button should be hidden even though we scrolled to top
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Wait for response to complete using alpha-view-compatible wait
    _wait_for_agent_idle_alpha(chat_panel)

    # After completion, button should still be hidden (at bottom via pin-to-bottom)
    _expect_jump_button_hidden(jump_btn)


@user_story("to verify user scroll during filling phase exits the anchor")
def test_user_scroll_exits_filling(sculptor_instance_: SculptorInstance) -> None:
    """Manually scrolling during the filling phase should disengage auto-scroll."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a streaming message
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_LONG_STREAM_TEXT}", "chunk_size": 100, "delay_seconds": 0.05}}`',
    )

    # Wait for streaming to start producing content
    page.wait_for_function(
        f"""() => document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"] [data-index="3"]') !== null"""
    )

    # Scroll away — this should exit filling and disengage auto-scroll
    scroll_alpha_chat_by(page, 300)

    # Jump button should appear since we scrolled away from the anchor
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible()

    # Wait for agent to finish before cleanup
    _wait_for_agent_idle_alpha(chat_panel, timeout=60000)


@user_story("to verify dynamic padding constrains scroll range for short responses")
def test_short_response_keeps_user_message_visible(sculptor_instance_: SculptorInstance) -> None:
    """After a short response completes, scrolling down maximally should not push
    the user message off the top of the viewport.  The dynamic paddingEnd should
    be just large enough for scroll-to-top to work, not more."""
    page = sculptor_instance_.page

    # Create a task with a short initial response
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Close the bottom panel (terminal) to maximize chat height — scroll tests
    # depend on having enough vertical space for dynamic padding math.
    # Must be done after workspace creation since the terminal only exists in workspaces.
    close_bottom_panel(page)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a follow-up message with a short response
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    _wait_for_agent_idle_alpha(chat_panel)

    # Try to scroll down as far as possible
    scroll_alpha_chat_by(page, 10000)

    # The last user message (data-index=2) should still be visible in the
    # viewport.  With proper dynamic padding, the scroll range is constrained
    # so the user message can't be pushed off-screen.
    page.wait_for_function(
        f"""() => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="2"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight;
        }}"""
    )


@user_story("to verify scroll-to-top works for the very first message in a conversation")
def test_scroll_to_top_first_message(sculptor_instance_: SculptorInstance) -> None:
    """The first user message in a new conversation should also scroll to the top.

    The alpha view must be mounted BEFORE the message is sent so the hook
    can detect the messageCount increase (0 -> 1) and fire scroll-to-top.
    We create the workspace without a prompt, then send the first message.
    """
    page = sculptor_instance_.page

    # Create a task WITHOUT an initial prompt so the chat starts empty.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="",
    )
    chat_panel = task_page.get_chat_panel()

    # Close the bottom panel (terminal) to maximize chat height.
    close_bottom_panel(page)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Use a short prompt so the user message itself fits inside the viewport.
    # fake_claude:stream_text embeds the full text in the prompt, so the user
    # message bubble contains whatever text we send.  If the user message is
    # taller than the viewport, pin-to-bottom fires the instant the assistant
    # starts responding and sweeps the message off-screen before the assertion
    # can observe it — the test isn't about overflow behavior, it's about
    # whether messageCount 0→1 positions the first user message at the top.
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )

    # The first user message (data-index=0) should be in the upper half of the
    # viewport, not pinned to the bottom.
    try:
        page.wait_for_function(
            f"""() => {{
                const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
                const item = container && container.querySelector('[data-index="0"]');
                if (!container || !item) return false;
                const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
                const halfHeight = container.clientHeight / 2;
                return offset >= 0 && offset < halfHeight;
            }}""",
        )
    except Exception:
        diag = get_message_top_offset(page, data_index=0)
        container_h = get_alpha_container_height(page)
        raise AssertionError(
            f"First user message not in upper half after scroll-to-top. offset={diag:.0f} containerH={container_h:.0f}"
        )

    _wait_for_agent_idle_alpha(chat_panel, timeout=60000)


@user_story("to verify auto-scroll re-engages after clicking jump-to-bottom during streaming")
def test_reengagement_after_scroll_to_top(sculptor_instance_: SculptorInstance) -> None:
    """After scroll-to-top and streaming, scrolling away then clicking jump-to-bottom
    should re-engage auto-scroll and pin to bottom."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a streaming message with a long response.  Use a slower chunk
    # delay (0.1s) so streaming lasts ~5s instead of ~2.5s — the test needs
    # streaming to still be active when we click jump-to-bottom (~2s later).
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_LONG_STREAM_TEXT}", "chunk_size": 100, "delay_seconds": 0.1}}`',
    )

    # Wait for streaming to produce content
    page.wait_for_function(
        f"""() => document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"] [data-index="3"]') !== null"""
    )

    # Scroll away — this should disengage auto-scroll
    scroll_alpha_chat_by(page, 300)

    # Jump button should be visible since we scrolled away
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible()

    # Click jump-to-bottom to re-engage auto-scroll
    jump_btn.click(force=True)

    # Verify auto-scroll re-engaged: we should be near the bottom while
    # streaming is still active.  Checking DURING streaming is more robust
    # than checking after streaming ends, because post-streaming layout
    # adjustments (paddingEnd recalculations, item re-measurements) can
    # shift the scroll position after the ResizeObserver disconnects.
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            if (!el) return false;
            return el.scrollHeight - el.scrollTop - el.clientHeight < 300;
        }}"""
    )

    # Wait for agent to finish before cleanup
    _wait_for_agent_idle_alpha(chat_panel, timeout=60000)


@user_story("to verify scroll-to-top works correctly for rapid successive sends")
def test_scroll_to_top_rapid_successive_sends(sculptor_instance_: SculptorInstance) -> None:
    """When the user sends a second message after the first response finishes streaming,
    the second message should also scroll to the top correctly."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Close the bottom panel to maximize chat height for scroll tests.
    # Must be done after workspace creation since the terminal only exists in workspaces.
    close_bottom_panel(page)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send first streaming message
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_LONG_STREAM_TEXT}", "chunk_size": 100, "delay_seconds": 0.05}}`',
    )
    _wait_for_agent_idle_alpha(chat_panel, timeout=60000)

    # Send second message with a short response
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    _wait_for_agent_idle_alpha(chat_panel)

    # The last user message (highest data-index user message) should be in the
    # upper half of the viewport after scroll-to-top.
    page.wait_for_function(
        f"""() => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            if (!container) return false;
            const items = container.querySelectorAll('[data-index]');
            let lastUserIdx = -1;
            for (const item of items) {{
                const idx = parseInt(item.getAttribute('data-index'), 10);
                if (idx > lastUserIdx && idx % 2 === 0 && idx >= 2) {{
                    lastUserIdx = idx;
                }}
            }}
            if (lastUserIdx < 0) return false;
            const item = container.querySelector('[data-index="' + lastUserIdx + '"]');
            if (!item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            const halfHeight = container.clientHeight / 2;
            return offset >= 0 && offset < halfHeight;
        }}"""
    )
