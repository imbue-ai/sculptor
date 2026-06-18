from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs


class PlaywrightPrPopoverElement:
    """Page Object Model for the PR button popover and its babysitter controls."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_chevron(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_CHEVRON)

    def get_babysitter_pause_toggle(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PR_BABYSITTER_PAUSE_TOGGLE)

    def get_babysitter_status(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PR_BABYSITTER_STATUS)
