from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightTopBarElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the TopBar component."""

    def get_command_palette_button(self) -> Locator:
        """Get the command palette open button (the search-icon button in the top bar)."""
        return self.get_by_test_id(ElementIDs.COMMAND_PALETTE_OPEN_BUTTON)

    def open_command_palette(self) -> None:
        """Click the command palette button to open the palette."""
        self.get_command_palette_button().click()
