"""Integration test for the smooth-streaming bottom sentinel wiring (SCU-1366).

The "disable smooth streaming when the message tail scrolls off-screen"
optimization relies on a bottom sentinel element that an ``IntersectionObserver``
watches.  ``useChatData`` creates and returns the sentinel ref via
``useSmoothStreamingViewportObserver``, but nothing ever attached it to a DOM
node, so ``sentinelRef.current`` was always ``null``: the observer was never
created and the optimization never activated.

This test pins the wiring at the UI layer:

1. A bottom sentinel element is present in the chat DOM (the ref is attached).
2. At the bottom of the conversation the sentinel is inside the viewport.
3. After scrolling up the sentinel leaves the viewport — the exact transition
   the ``IntersectionObserver`` keys off to toggle smooth streaming.

Before the fix step 1 already fails (no sentinel element is rendered).
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A long response repeated enough times that four of them overflow the chat
# viewport and make the scroll container scrollable.
_LONG_TEXT = " ".join(["This is a longer response that should take up some space."] * 20)


def _wait_for_agent_idle(page: Page, *, timeout: int = 30000) -> None:
    """Wait for the agent to finish by checking the StatusPill disappears."""
    status_pill = page.get_by_test_id(ElementIDs.STATUS_PILL)
    expect(status_pill).not_to_be_visible(timeout=timeout)


@user_story("to disable smooth streaming when the message tail scrolls off-screen")
def test_bottom_sentinel_is_attached_and_tracks_viewport(sculptor_instance_: SculptorInstance) -> None:
    """The chat must render a bottom sentinel element that tracks the viewport.

    This is the DOM wiring the smooth-streaming viewport optimization depends
    on; without it the IntersectionObserver is never created and smooth
    streaming stays permanently enabled.
    """
    page = sculptor_instance_.page

    # Build a conversation tall enough to make the chat scrollable.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(chat_panel, f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    _wait_for_agent_idle(page)

    # 1. The bottom sentinel element must exist in the DOM.  Before the fix the
    #    ref returned by useChatData was never attached, so no sentinel was
    #    rendered and this assertion fails (0 elements found).
    sentinel = page.get_by_test_id(ElementIDs.ALPHA_CHAT_BOTTOM_SENTINEL)
    expect(sentinel).to_have_count(1)

    # 2. At the bottom of the conversation the sentinel is within the viewport.
    #    to_be_in_viewport uses an IntersectionObserver against the viewport —
    #    the same mechanism the production hook relies on.
    scroll_alpha_chat_by(page, 10000)
    expect(sentinel).to_be_in_viewport()

    # 3. Scrolling up moves the message tail (and the sentinel) off-screen.  The
    #    sentinel is clipped by the chat scroll container, so it stops
    #    intersecting the viewport — exactly the transition that disables smooth
    #    streaming when the tail is no longer visible.
    scroll_alpha_chat_to_top(page)
    expect(sentinel).not_to_be_in_viewport()
