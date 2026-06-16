from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightBtwPopupElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the by-the-way (BTW) popup."""

    def get_question(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BTW_POPUP_QUESTION)

    def get_answer(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BTW_POPUP_ANSWER)

    def get_close_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BTW_POPUP_CLOSE_BUTTON)

    def get_drag_handle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BTW_POPUP_DRAG_HANDLE)


def get_btw_popup(page: Page) -> PlaywrightBtwPopupElement:
    """Get the by-the-way (BTW) popup element from the page."""
    locator = page.get_by_test_id(ElementIDs.BTW_POPUP)
    return PlaywrightBtwPopupElement(locator=locator, page=page)
