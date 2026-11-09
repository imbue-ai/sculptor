from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightJjSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Jujutsu section in Settings."""

    def get_availability(self) -> Locator:
        """Get the JJ_AVAILABLE callout (or its loading placeholder)."""
        return self.get_by_test_id(ElementIDs.JJ_AVAILABILITY)

    def get_recheck_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.JJ_RECHECK_BUTTON)

    def get_mode_selector(self) -> Locator:
        """Get the Binary-Source (MANAGED/CUSTOM) selector."""
        return self.get_by_test_id(ElementIDs.JJ_MODE_SELECTOR)

    def get_mode_option_managed(self) -> Locator:
        # Radix Select options render in a page-level portal, not inside the section.
        return self._page.get_by_test_id(ElementIDs.JJ_MODE_OPTION_MANAGED)

    def get_status(self) -> Locator:
        return self.get_by_test_id(ElementIDs.JJ_STATUS)

    def get_up_to_date(self) -> Locator:
        """Get the in-range status text (shown when jj is installed at or above the minimum)."""
        return self.get_by_test_id(ElementIDs.JJ_UP_TO_DATE)

    def get_install_button(self) -> Locator:
        """Get the managed Install/Retry button."""
        return self.get_by_test_id(ElementIDs.JJ_INSTALL_BUTTON)

    def get_identity(self) -> Locator:
        """Get the read-only identity text."""
        return self.get_by_test_id(ElementIDs.JJ_IDENTITY)

    def get_identity_form(self) -> Locator:
        return self.get_by_test_id(ElementIDs.JJ_IDENTITY_FORM)

    def get_identity_name_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.JJ_IDENTITY_NAME_INPUT)

    def get_identity_email_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.JJ_IDENTITY_EMAIL_INPUT)

    def get_identity_submit(self) -> Locator:
        return self.get_by_test_id(ElementIDs.JJ_IDENTITY_SUBMIT)
