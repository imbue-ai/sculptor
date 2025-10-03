from sculptor.constants import ElementIDs
from sculptor.testing.elements.onboarding import PlaywrightInstallationStepElement
from sculptor.testing.elements.onboarding import PlaywrightWelcomeStepElement
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage


class PlaywrightOnboardingPage(PlaywrightIntegrationTestPage):
    """Page object for the onboarding wizard - provides access to step components."""

    def get_welcome_step(self) -> PlaywrightWelcomeStepElement:
        """Get the email step component."""
        email_step_locator = self.get_by_test_id(ElementIDs.ONBOARDING_WELCOME_STEP)
        return PlaywrightWelcomeStepElement(locator=email_step_locator, page=self._page)

    def get_installation_step(self) -> PlaywrightInstallationStepElement:
        """Get the installation step component."""
        installation_step_locator = self.get_by_test_id(ElementIDs.ONBOARDING_INSTALLATION_STEP)
        return PlaywrightInstallationStepElement(locator=installation_step_locator, page=self._page)
