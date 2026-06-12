from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs


class PlaywrightSetupStatusElement:
    """Page Object Model for the workspace setup status card and config prompt."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_card(self) -> Locator:
        """Get the setup status card locator."""
        return self._page.get_by_test_id(ElementIDs.SETUP_STATUS_CARD)

    def get_output(self) -> Locator:
        """Get the setup command output locator."""
        return self._page.get_by_test_id(ElementIDs.SETUP_STATUS_OUTPUT)

    def get_edit_button(self) -> Locator:
        """Get the pencil edit button on the setup status card."""
        return self._page.get_by_test_id(ElementIDs.SETUP_EDIT_BUTTON).first

    def get_config_prompt(self) -> Locator:
        """Get the configure-CTA prompt shown when no setup command is set."""
        return self._page.get_by_test_id(ElementIDs.SETUP_CONFIG_PROMPT)

    def get_rerun_button(self) -> Locator:
        """Get the rerun button on the setup status card."""
        return self._page.get_by_test_id(ElementIDs.SETUP_RERUN_BUTTON)

    def get_cancel_button(self) -> Locator:
        """Get the cancel button shown during a running setup."""
        return self._page.get_by_test_id(ElementIDs.SETUP_CANCEL_BUTTON)

    def get_run_button(self) -> Locator:
        """Get the run-setup button shown when a command was added after workspace creation."""
        return self._page.get_by_test_id(ElementIDs.SETUP_RUN_BUTTON)

    def get_truncation_banner(self) -> Locator:
        """Get the truncation banner shown when setup output overflowed."""
        return self._page.get_by_test_id(ElementIDs.SETUP_STATUS_TRUNCATION)

    def get_config_settings_link(self) -> Locator:
        """Get the settings deep-link inside the config prompt CTA."""
        return self._page.get_by_test_id(ElementIDs.SETUP_CONFIG_SETTINGS_LINK)
