from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.hotkey_field import PlaywrightHotkeyFieldElement


class PlaywrightKeybindingsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Keybindings Settings section."""

    def set_global_hotkey(self, keys: str) -> None:
        """Set the global hotkey by simulating key press."""
        self._get_global_hotkey_field().set_hotkey(keys)

    def clear_global_hotkey(self) -> None:
        """Clear the global hotkey."""
        self._get_global_hotkey_field().clear_hotkey()

    def set_new_agent_hotkey(self, keys: str) -> None:
        """Set the new agent hotkey by simulating key press."""
        self._get_new_agent_hotkey_field().set_hotkey(keys)

    def clear_new_agent_hotkey(self) -> None:
        """Clear the new agent hotkey."""
        self._get_new_agent_hotkey_field().clear_hotkey()

    def set_search_agents_hotkey(self, keys: str) -> None:
        """Set the search agents hotkey by simulating key press."""
        self._get_search_agents_hotkey_field().set_hotkey(keys)

    def clear_search_agents_hotkey(self) -> None:
        """Clear the search agents hotkey."""
        self._get_search_agents_hotkey_field().clear_hotkey()

    def set_toggle_sidebar_hotkey(self, keys: str) -> None:
        """Set the toggle sidebar hotkey by simulating key press."""
        self._get_toggle_sidebar_hotkey_field().set_hotkey(keys)

    def clear_toggle_sidebar_hotkey(self) -> None:
        """Clear the toggle sidebar hotkey."""
        self._get_toggle_sidebar_hotkey_field().clear_hotkey()

    def _get_global_hotkey_field(self) -> PlaywrightHotkeyFieldElement:
        """Get the global hotkey field element."""
        field_locator = self.get_by_test_id(ElementIDs.SETTINGS_GLOBAL_HOTKEY_FIELD)
        return PlaywrightHotkeyFieldElement(locator=field_locator, page=self._page)

    def _get_new_agent_hotkey_field(self) -> PlaywrightHotkeyFieldElement:
        """Get the new agent hotkey field element."""
        field_locator = self.get_by_test_id(ElementIDs.SETTINGS_NEW_AGENT_HOTKEY_FIELD)
        return PlaywrightHotkeyFieldElement(locator=field_locator, page=self._page)

    def _get_search_agents_hotkey_field(self) -> PlaywrightHotkeyFieldElement:
        """Get the search agents hotkey field element."""
        field_locator = self.get_by_test_id(ElementIDs.SETTINGS_SEARCH_AGENTS_HOTKEY_FIELD)
        return PlaywrightHotkeyFieldElement(locator=field_locator, page=self._page)

    def _get_toggle_sidebar_hotkey_field(self) -> PlaywrightHotkeyFieldElement:
        """Get the toggle sidebar hotkey field element."""
        field_locator = self.get_by_test_id(ElementIDs.SETTINGS_TOGGLE_SIDEBAR_HOTKEY_FIELD)
        return PlaywrightHotkeyFieldElement(locator=field_locator, page=self._page)
