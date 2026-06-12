from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightLightboxElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the image lightbox overlay."""

    def __init__(self, page: Page) -> None:
        locator = page.get_by_test_id(ElementIDs.LIGHTBOX_NAV_PREVIOUS)
        super().__init__(locator=locator, page=page)

    def get_nav_previous(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LIGHTBOX_NAV_PREVIOUS)

    def get_nav_next(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LIGHTBOX_NAV_NEXT)

    def get_counter(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LIGHTBOX_COUNTER)
