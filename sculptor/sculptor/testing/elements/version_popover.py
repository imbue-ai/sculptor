from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightVersionPopoverElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Version Popover and related update indicators."""

    def __init__(self, page: Page) -> None:
        locator = page.get_by_test_id(ElementIDs.VERSION_POPOVER_CONTENT)
        super().__init__(locator=locator, page=page)

    def get_trigger(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.VERSION)

    def open(self) -> None:
        self.get_trigger().click()

    def get_channel(self) -> Locator:
        return self.get_by_test_id(ElementIDs.VERSION_POPOVER_CHANNEL)

    def get_status(self) -> Locator:
        return self.get_by_test_id(ElementIDs.VERSION_POPOVER_STATUS)

    def get_restart_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.VERSION_POPOVER_RESTART_BUTTON)

    def get_claude_cli_version(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_VERSION_POPOVER)

    def get_claude_cli_mode(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_MODE_POPOVER)

    def get_update_dot(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.UPDATE_DOT)
