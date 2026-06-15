from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# Upper bound on dismiss clicks so a toast that refuses to unmount can't spin
# the loop forever; the trailing ``expect(...).to_have_count(0)`` still asserts
# that every visible toast was actually dismissed.
_MAX_DISMISS_ATTEMPTS = 10


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

    def dismiss_all(self) -> None:
        """Dismiss all currently-visible toasts by clicking their close buttons."""
        # Only consider *visible* close buttons. A toast that is mid-unmount
        # lingers in the DOM but is not visible (SCU-1413): counting it makes
        # ``.first`` select it, and a normal click then hangs for the full
        # actionability timeout waiting for it to become visible. A toast that is
        # still sliding in IS visible (opacity is full throughout the slideIn),
        # so it stays in scope and the normal click waits for Playwright's
        # stability / in-viewport checks before landing. We deliberately do not
        # use ``force`` here: force skips the in-viewport check (so it errors on a
        # button still off-screen mid-slide) and hit-testing (so it can land on a
        # still-moving button and silently miss, never dismissing it).
        buttons = self.get_close_buttons().filter(visible=True)
        for _ in range(_MAX_DISMISS_ATTEMPTS):
            count = buttons.count()
            if count == 0:
                break
            buttons.first.click()
            expect(buttons).to_have_count(count - 1)
        expect(buttons).to_have_count(0)
