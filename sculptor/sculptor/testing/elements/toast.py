from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# Upper bound on dismiss clicks so a toast that refuses to unmount can't spin
# the loop forever; the trailing ``expect(...).to_have_count(0)`` still asserts
# that every open toast was actually dismissed.
_MAX_DISMISS_ATTEMPTS = 10

# Per-click actionability budget. A close button that is mid-slide-in finishes
# its 150ms animation well within this; a click that loses a race to a toast
# already unmounting fails fast (so we re-resolve and continue) instead of
# burning the full default 30s actionability timeout.
_DISMISS_CLICK_TIMEOUT_MS = 5_000


class PlaywrightToastElement(PlaywrightIntegrationTestElement):
    """Page Object Model for toast notifications."""

    def __init__(self, page: Page) -> None:
        locator = page.get_by_test_id(ElementIDs.TOAST)
        super().__init__(locator=locator, page=page)

    def get_toasts(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TOAST)

    def filter_by_text(self, text: str) -> Locator:
        return self.get_toasts().filter(has_text=text)

    def get_close_buttons(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TOAST_CLOSE_BUTTON)

    def get_action_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TOAST_ACTION_BUTTON)

    def _get_open_close_buttons(self) -> Locator:
        """Close buttons of toasts that are open — not mid-unmount.

        Radix stamps ``data-state="open"`` on a toast Root while it is shown
        (throughout the 150ms slideIn) and flips it to ``data-state="closed"``
        the instant the user dismisses it, during the ~100ms hide animation
        before the Root unmounts. A ``data-state="closed"`` toast lingers in the
        DOM but is on its way out (SCU-1413): a click that lands on its close
        button never sees a "visible, enabled and stable" element, so it burns
        the full actionability timeout. Scoping to ``data-state="open"`` Roots
        keeps sliding-in toasts in range (they are still ``open``) while
        excluding the unmounting ones.
        """
        open_toasts = self.get_toasts().and_(self._page.locator('[data-state="open"]'))
        return open_toasts.get_by_test_id(ElementIDs.TOAST_CLOSE_BUTTON)

    def dismiss_all(self) -> None:
        """Dismiss all open toasts by clicking their close buttons.

        Each close button is re-resolved per iteration and clicked with a
        bounded timeout: a click that loses a race to a toast that just began
        unmounting (so it no longer matches ``data-state="open"``) fails fast,
        and we re-resolve from the settled DOM rather than burning the full
        default actionability timeout. We deliberately do not use ``force``:
        force skips the in-viewport check (so it errors on a button still
        off-screen mid-slide) and hit-testing (so it can land on a still-moving
        button and silently miss, never dismissing it).
        """
        buttons = self._get_open_close_buttons()
        for _ in range(_MAX_DISMISS_ATTEMPTS):
            count = buttons.count()
            if count == 0:
                break
            try:
                buttons.first.click(timeout=_DISMISS_CLICK_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                # The targeted toast unmounted out from under the click; the
                # loop re-resolves against the now-settled open toasts.
                continue
            expect(buttons).to_have_count(count - 1)
        expect(buttons).to_have_count(0)
