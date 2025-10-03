from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightHotkeyFieldElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the HotkeyField component."""

    def set_hotkey(self, keys: str) -> None:
        """Set the hotkey by simulating key press."""
        # Click the set button to start recording
        self._get_set_button().click()

        # Simulate the key combination
        self._page.keyboard.press(keys)

    def clear_hotkey(self) -> None:
        """Clear the hotkey."""
        self._get_clear_button().click()

    def _get_set_button(self) -> Locator:
        """Get the set button within this hotkey field."""
        return self.get_by_test_id(ElementIDs.SETTINGS_HOTKEY_SET_BUTTON)

    def _get_clear_button(self) -> Locator:
        """Get the clear button within this hotkey field."""
        return self.get_by_test_id(ElementIDs.SETTINGS_HOTKEY_CLEAR_BUTTON)
