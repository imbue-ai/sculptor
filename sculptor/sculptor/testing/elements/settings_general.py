from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGeneralSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the General section in Settings."""

    def get_tidy_confirmation_switch(self) -> Locator:
        """The "Confirm before tidying panels" switch.

        Inverted relative to the underlying suppression flag: checked means tidy
        confirmations are shown (the default), unchecked means layouts tidy silently.
        """
        return self.get_by_test_id(ElementIDs.SETTINGS_TIDY_CONFIRMATION_SWITCH)
