from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightSettingsUpdateElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the auto-update controls on the Settings page."""

    def __init__(self, page: Page) -> None:
        locator = page.get_by_test_id(ElementIDs.SETTINGS_CHECK_FOR_UPDATES_BUTTON)
        super().__init__(locator=locator, page=page)

    def get_channel_select(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_UPDATE_CHANNEL_SELECT)

    def get_channel_option_rc(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_UPDATE_CHANNEL_OPTION_RC)

    def get_channel_option_stable(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_UPDATE_CHANNEL_OPTION_STABLE)

    def get_check_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_CHECK_FOR_UPDATES_BUTTON)
