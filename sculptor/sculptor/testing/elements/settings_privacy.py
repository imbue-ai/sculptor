from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightPrivacySettingsElement(PlaywrightIntegrationTestElement):
    """Element for the Settings → Privacy section (email field + telemetry switch)."""

    def get_email_field(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_EMAIL_FIELD)

    def get_telemetry_row(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_PRIVACY_TELEMETRY_ROW)

    def get_telemetry_switch(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_PRIVACY_TELEMETRY_SWITCH)

    def get_opt_out_dialog(self) -> Locator:
        # The confirmation dialog renders in a portal outside the settings
        # content, so it is located from the page root.
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PRIVACY_TELEMETRY_DIALOG)

    def get_opt_out_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PRIVACY_TELEMETRY_DIALOG_CONFIRM)

    def get_opt_out_cancel_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PRIVACY_TELEMETRY_DIALOG_CANCEL)

    def disable_telemetry(self) -> None:
        """Turn the telemetry switch off, confirming through the dialog."""
        self.get_telemetry_switch().click()
        confirm_button = self.get_opt_out_confirm_button()
        expect(confirm_button).to_be_visible()
        confirm_button.click()
        expect(self.get_opt_out_dialog()).not_to_be_visible()

    def enable_telemetry(self) -> None:
        """Turn the telemetry switch on (asymmetric flow: no confirmation dialog)."""
        self.get_telemetry_switch().click()
