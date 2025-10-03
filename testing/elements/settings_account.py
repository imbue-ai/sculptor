from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightAccountSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Account Settings section."""

    def edit_git_username(self, username: str) -> None:
        """Edit the git username field with a new value."""
        # Click the field to enter edit mode
        self._get_git_username_edit_button().click()

        # Fill the input with the new username
        input_field = self._get_git_username_input()
        input_field.fill(username)

        # Save the changes
        self._get_git_username_save_button().click()

    def select_telemetry_level(self, level: str) -> None:
        """Select a telemetry level from the dropdown."""
        self._get_telemetry_select().click()
        options = self._page.get_by_test_id(ElementIDs.SETTINGS_TELEMETRY_OPTION)
        found_option = None
        for option in options.all():
            if option.inner_text() == level:
                if found_option:
                    raise ValueError(f"Multiple telemetry level options found for '{level}'")
                found_option = option
        if not found_option:
            raise ValueError(f"Telemetry level option '{level}' not found")
        found_option.click()

    def _get_email_field(self) -> Locator:
        """Get the email field."""
        return self.get_by_test_id(ElementIDs.SETTINGS_EMAIL_FIELD)

    def _get_git_username_field(self) -> Locator:
        """Get the git username field."""
        return self.get_by_test_id(ElementIDs.SETTINGS_GIT_USERNAME_FIELD)

    def _get_git_username_input(self) -> Locator:
        """Get the git username input field."""
        return self.get_by_test_id(ElementIDs.SETTINGS_GIT_USERNAME_INPUT)

    def _get_git_username_edit_button(self) -> Locator:
        """Get the git username edit button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_GIT_USERNAME_EDIT_BUTTON)

    def _get_git_username_save_button(self) -> Locator:
        """Get the git username save button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_GIT_USERNAME_SAVE_BUTTON)

    def _get_telemetry_select(self) -> Locator:
        """Get the telemetry select dropdown."""
        return self.get_by_test_id(ElementIDs.SETTINGS_TELEMETRY_SELECT)

    def _get_anthropic_auth_button(self) -> Locator:
        """Get the Anthropic authentication button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ANTHROPIC_AUTH_BUTTON)
