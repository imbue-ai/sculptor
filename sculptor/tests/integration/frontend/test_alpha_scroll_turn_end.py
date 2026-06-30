"""Integration test: the chat does not jump when the agent finishes its turn.

The alpha-chat scroll system is an explicit state machine (see
``docs/development/scroll_state_unification.md``, SCU-1566). While ``following``
the live tail, the design pins the last message's *content* bottom flush with the
viewport bottom, leaving the dynamic ``paddingEnd`` as empty slack *below*
``scrollTop`` (``distanceFromContentBottom == 0``).

A regression had the pin land at TanStack's ``getMaxScrollOffset()`` instead — the
very bottom of the padded scroll range — which parks ``scrollTop`` inside the
``paddingEnd`` gap with zero slack. That floated the last line a ``paddingEnd``-tall
gap above the viewport bottom *and* left no room for the last message to shrink when
the turn ends (its streaming cursor is removed): the browser clamped ``scrollTop``
down by the shrink and the whole conversation jumped up by a small, annoying amount.

This test sends a follow-on streaming message in a longer chat, lets it overflow and
pin to the bottom, and asserts the last message sits flush with the viewport bottom
while following — directly the property whose absence caused the turn-end jump.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_max_following_tail_gap
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import close_bottom_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Long history responses so the chat is comfortably scrollable.
_LONG_TEXT = "Lorem ipsum dolor sit amet. " * 120
# A long streaming response (~5k chars over ~10s) that overflows the viewport and
# pins to the bottom while it streams.
_STREAM_TEXT = "The quick brown fox jumps over the lazy dog. " * 112

# While following, the last message's bottom may sit a few px above the viewport
# bottom (message margins, sub-pixel rounding), but never the full ~64px paddingEnd
# gap of the bug. (Measured: ~64px before the fix, ~0px after.)
_FLUSH_TOLERANCE_PX = 24


@user_story("to not have the chat jump when the agent finishes its turn (req: stable turn-end)")
def test_following_pins_last_message_flush_to_viewport_bottom(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    close_bottom_panel(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # A bit of history so the follow-on user message scrolls off the top and we
    # genuinely follow the live tail (rather than anchoring a short turn).
    send_chat_message(chat_panel, f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    view = get_alpha_chat_view(page)
    expect(view).to_be_visible()

    # The follow-on streaming message: overflows the viewport and pins to the bottom.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )

    # Wait until we are following the live tail, then let it stream for a span so the
    # measurement is taken mid-stream (well before the turn ends).
    expect(view).to_have_attribute("data-scroll-phase", "following", timeout=30_000)
    page.wait_for_timeout(1500)
    expect(view).to_have_attribute("data-scroll-phase", "following")

    max_gap = get_max_following_tail_gap(page)

    # While following, the last message stays flush with the viewport bottom — it is
    # not parked in the paddingEnd gap (the ~64px regression that produced the
    # turn-end jump, because there was no slack for the last message to shrink into).
    assert max_gap is not None, "alpha chat view or its messages not found while following"
    assert max_gap <= _FLUSH_TOLERANCE_PX, (
        f"while following, the last message floated {max_gap}px above the viewport bottom "
        + f"(expected <= {_FLUSH_TOLERANCE_PX}px); the pin is parking in the paddingEnd gap"
    )

    # Let the turn finish cleanly before the test ends.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)
