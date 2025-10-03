from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWelcomeStepElement(PlaywrightIntegrationTestElement):
    """Element representing the email/welcome step of onboarding."""

    def get_email_input(self) -> Locator:
        """Get the email input field."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_EMAIL_INPUT)

    def get_submit_button(self) -> Locator:
        """Get the email submit button."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_EMAIL_SUBMIT)

    def enter_email(self, email: str) -> None:
        """Enter email in the input field."""
        email_input = self.get_email_input()
        email_input.click()
        email_input.type(email)

    def submit(self) -> None:
        """Submit the email form."""
        self.get_submit_button().click()

    def complete_step(self, email: str) -> None:
        """Complete the entire email step."""
        self.enter_email(email)
        self.submit()


class PlaywrightApiKeyModalElement(PlaywrightIntegrationTestElement):
    """Element representing the API key modal within the installation step."""

    def get_api_key_input(self) -> Locator:
        """Get the API key input field."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_API_KEY_INPUT)

    def get_submit_button(self) -> Locator:
        """Get the API key submit button."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_API_KEY_SUBMIT)

    def enter_api_key(self, api_key: str) -> None:
        """Enter API key in the input field."""
        api_key_input = self.get_api_key_input()
        api_key_input.click()
        api_key_input.type(api_key)

    def submit(self) -> None:
        """Submit the API key form."""
        self.get_submit_button().click()

    def complete_api_key_entry(self, api_key: str) -> None:
        """Complete the API key entry process."""
        self.enter_api_key(api_key)
        self.submit()


class PlaywrightAnthropicAccessModalElement(PlaywrightIntegrationTestElement):
    def get_api_key_modal_open_button(self) -> Locator:
        """Get the button to open the API key modal."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_API_KEY_MODAL_OPEN_BUTTON)

    def get_api_key_modal(self) -> PlaywrightApiKeyModalElement:
        """Get the API key modal element."""
        modal = self._page.get_by_test_id(ElementIDs.ONBOARDING_API_KEY_MODAL)
        return PlaywrightApiKeyModalElement(locator=modal, page=self._page)

    def open_api_key_modal(self) -> PlaywrightApiKeyModalElement:
        """Open the API key modal."""
        self.get_api_key_modal_open_button().click()
        # Verify modal is visible
        modal = self.get_api_key_modal()
        expect(modal).to_be_visible()
        return modal


class PlaywrightInstallationStepElement(PlaywrightIntegrationTestElement):
    """Element representing the installation step of onboarding."""

    def get_anthropic_access_modal_open_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ONBOARDING_ANTHROPIC_ACCESS_MODAL_OPEN_BUTTON)

    def get_anthropic_access_modal(self) -> PlaywrightApiKeyModalElement:
        modal = self._page.get_by_test_id(ElementIDs.ONBOARDING_ANTHROPIC_ACCESS_MODAL)
        return PlaywrightAnthropicAccessModalElement(locator=modal, page=self._page)

    def get_telemetry_selector(self) -> Locator:
        """Get the telemetry level selector."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_TELEMETRY_SELECTOR)

    def get_telemetry_options(self) -> Locator:
        """Get all telemetry options."""
        return self._page.get_by_test_id(ElementIDs.ONBOARDING_TELEMETRY_OPTION)

    def get_complete_button(self) -> Locator:
        """Get the onboarding complete button."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_COMPLETE_BUTTON)

    def get_back_button(self) -> Locator:
        """Get the back button."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_BACK_BUTTON)

    def open_anthropic_access_modal(self) -> PlaywrightAnthropicAccessModalElement:
        self.get_anthropic_access_modal_open_button().click()
        modal = self.get_anthropic_access_modal()
        expect(modal).to_be_visible()
        return modal

    def complete_api_key_setup(self, api_key: str) -> None:
        """Complete API key setup via modal."""
        anthropic_access_modal = self.open_anthropic_access_modal()
        api_key_modal = anthropic_access_modal.open_api_key_modal()

        api_key_input = api_key_modal.get_api_key_input()
        expect(api_key_input).to_be_visible()

        api_key_modal.complete_api_key_entry(api_key)

    def select_telemetry_option(self, option_index: int) -> None:
        """Select a telemetry option by index (0-based)."""
        telemetry_selector = self.get_telemetry_selector()
        telemetry_selector.click()

        telemetry_options = self.get_telemetry_options()
        expect(telemetry_options).to_have_count(3)
        telemetry_options.nth(option_index).click()

    def submit(self) -> None:
        """Submit the installation step."""
        self.get_complete_button().click()

    def go_back(self) -> None:
        """Go back to the previous step."""
        self.get_back_button().click()

    def complete_step(self, api_key: str, telemetry_option_index: int = 1) -> None:
        """Complete the entire installation step."""
        self.complete_api_key_setup(api_key)
        self.select_telemetry_option(telemetry_option_index)
        self.submit()
