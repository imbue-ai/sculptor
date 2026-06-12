from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs


class PlaywrightZenModeElement:
    """POM for zen mode exit controls."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_exit_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.EXIT_ZEN_MODE_BUTTON)

    def hover_exit_hot_zone(self) -> None:
        self._page.mouse.move(100, 40)
