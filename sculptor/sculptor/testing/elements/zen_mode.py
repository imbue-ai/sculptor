from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs

# A point inside the top-left hot zone that reveals the zen mode exit button on hover.
_EXIT_HOT_ZONE_HOVER_X = 100
_EXIT_HOT_ZONE_HOVER_Y = 40


class PlaywrightZenModeElement:
    """POM for zen mode exit controls."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_exit_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.EXIT_ZEN_MODE_BUTTON)

    def hover_exit_hot_zone(self) -> None:
        self._page.mouse.move(_EXIT_HOT_ZONE_HOVER_X, _EXIT_HOT_ZONE_HOVER_Y)
