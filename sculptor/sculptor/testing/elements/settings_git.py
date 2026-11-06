from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGitSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Git section in Settings."""

    def get_creation_prompt_textarea(self) -> Locator:
        """Get the textarea for editing the PR creation prompt."""
        return self._locator.locator("textarea")

    def get_poll_interval_input(self) -> Locator:
        """Get the number input for poll interval."""
        return self._locator.get_by_test_id(ElementIDs.SETTINGS_POLL_INTERVAL_INPUT)

    def set_poll_interval(self, seconds: int) -> None:
        """Clear and fill the poll interval input, then blur to save."""
        input_field = self.get_poll_interval_input()
        input_field.fill(str(seconds))
        input_field.blur()
