from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightClaudeCliSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Dependencies section in Settings (Claude + Git)."""

    # ── Claude ──

    def get_mode_selector(self) -> Locator:
        """Get the binary mode selector."""
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_MODE_SELECTOR)

    def get_version(self) -> Locator:
        """Get the version display element."""
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_VERSION)

    def get_status(self) -> Locator:
        """Get the status display element."""
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_STATUS)

    def get_install_button(self) -> Locator:
        """Get the install/retry button."""
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_INSTALL_BUTTON)

    def get_up_to_date(self) -> Locator:
        """Get the 'Up to date' text element."""
        return self.get_by_test_id(ElementIDs.CLAUDE_CLI_UP_TO_DATE)

    def get_mode_option_managed(self) -> Locator:
        """Get the Managed mode option in the selector dropdown."""
        return self._page.get_by_test_id(ElementIDs.CLAUDE_CLI_MODE_OPTION_MANAGED)

    def get_mode_option_custom(self) -> Locator:
        """Get the Custom mode option in the selector dropdown."""
        return self._page.get_by_test_id(ElementIDs.CLAUDE_CLI_MODE_OPTION_CUSTOM)

    def get_settling_spinner(self) -> Locator:
        """Get the mode-change settling spinner."""
        return self._page.get_by_test_id(ElementIDs.CLAUDE_CLI_MODE_SETTLING)

    # ── Git ──

    def get_git_status(self) -> Locator:
        """Get the Git status display element."""
        return self.get_by_test_id(ElementIDs.SETTINGS_GIT_DEP_STATUS)
