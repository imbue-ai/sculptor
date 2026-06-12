from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.hotkey_field import PlaywrightHotkeyFieldElement


class PlaywrightKeybindingsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Keybindings Settings section."""

    def get_keybinding_row(self, keybinding_id: str) -> Locator:
        """Find a keybinding row by its data-keybinding-id attribute."""
        return self._locator.locator(f'[data-keybinding-id="{keybinding_id}"]')

    def get_hotkey_field(self, keybinding_id: str) -> PlaywrightHotkeyFieldElement:
        """Get the HotkeyField element within a keybinding row."""
        row = self.get_keybinding_row(keybinding_id)
        return PlaywrightHotkeyFieldElement(locator=row, page=self._page)

    def set_keybinding(self, keybinding_id: str, keys: str) -> None:
        """Click the binding display to enter recording, then press the keys."""
        self.get_hotkey_field(keybinding_id).set_hotkey(keys)

    def clear_keybinding(self, keybinding_id: str) -> None:
        """Click the clear button on a keybinding row."""
        self.get_hotkey_field(keybinding_id).clear_hotkey()

    def get_keybinding_display_text(self, keybinding_id: str) -> Locator:
        """Return the set button locator (which displays the current binding text)."""
        row = self.get_keybinding_row(keybinding_id)
        return row.get_by_test_id(ElementIDs.SETTINGS_HOTKEY_SET_BUTTON)

    def get_search_field(self) -> Locator:
        """Return the search bar locator."""
        return self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_SEARCH)

    def search(self, query: str) -> None:
        """Type into the search bar."""
        self.get_search_field().fill(query)

    def clear_search(self) -> None:
        """Clear the search bar."""
        search_input = self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_SEARCH)
        search_input.fill("")

    def reset_all_to_defaults(self) -> None:
        """Click the 'Reset all to defaults' button."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_RESET_ALL).click()

    def get_conflict_warning(self) -> Locator:
        """Return the conflict warning locator."""
        return self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_CONFLICT_WARNING)

    def click_reassign(self) -> None:
        """Click the 'Reassign' button in the conflict warning."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_REASSIGN).click()

    def click_cancel_conflict(self) -> None:
        """Click the 'Cancel' button in the conflict warning."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_CANCEL_CONFLICT).click()
