from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.settings_account import PlaywrightAccountSettingsElement
from sculptor.testing.elements.settings_general import PlaywrightGeneralSettingsElement
from sculptor.testing.elements.settings_keybindings import PlaywrightKeybindingsSettingsElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightSettingsPage(PlaywrightProjectLayoutPage):
    """Page Object Model for the Settings page."""

    def click_on_general(self) -> PlaywrightGeneralSettingsElement:
        """Navigate to General settings and return the section element."""
        self._get_general_nav().click()
        # Return the general settings section scoped to the page
        return PlaywrightGeneralSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_keybindings(self) -> PlaywrightKeybindingsSettingsElement:
        """Navigate to Keybindings settings and return the section element."""
        self._get_keybindings_nav().click()
        # Return the keybindings settings section scoped to the page
        return PlaywrightKeybindingsSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_account(self) -> PlaywrightAccountSettingsElement:
        """Navigate to Account settings and return the section element."""
        self._get_account_nav().click()
        # Return the account settings section scoped to the page
        return PlaywrightAccountSettingsElement(locator=self._get_settings_content(), page=self._page)

    def _get_settings_content(self) -> Locator:
        """Get the main settings page container."""
        return self.get_by_test_id(ElementIDs.SETTINGS_CONTENT)

    def _get_general_nav(self) -> Locator:
        """Get the General navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_GENERAL)

    def _get_keybindings_nav(self) -> Locator:
        """Get the Keybindings navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_KEYBINDINGS)

    def _get_account_nav(self) -> Locator:
        """Get the Account navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_ACCOUNT)
