from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightEnvVarsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Environment Variables section in Settings."""

    def get_override_toggle(self) -> Locator:
        """Get the override toggle switch."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ENV_VAR_OVERRIDE_TOGGLE)

    def get_names_list(self) -> Locator:
        """Get the loaded variable names container."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ENV_VAR_NAMES_LIST)

    def get_setup_instructions(self) -> Locator:
        """Get the setup instructions element referencing the .env file path."""
        return self.get_by_text(".sculptor/.env").first

    def get_no_variables_message(self) -> Locator:
        """Get the 'No variables loaded' message within the names list."""
        return self.get_names_list().get_by_text("No variables loaded", exact=False)
