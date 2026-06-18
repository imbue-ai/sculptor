from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightCIBabysitterSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the CI Babysitter Settings section."""

    def get_enable_toggle(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_CI_BABYSITTER_ENABLED_TOGGLE)

    def enable(self) -> None:
        """Turn the CI Babysitter on (idempotent)."""
        toggle = self.get_enable_toggle()
        expect(toggle).to_be_visible()
        if toggle.get_attribute("data-state") != "checked":
            toggle.click()
        expect(toggle).to_have_attribute("data-state", "checked")

    def open_agent_select(self) -> None:
        """Open the 'Babysitter agent' Select dropdown."""
        trigger = self._page.get_by_test_id(ElementIDs.SETTINGS_CI_BABYSITTER_AGENT_SELECT)
        expect(trigger).to_be_visible()
        trigger.click()

    def get_agent_option(self, label: str) -> Locator:
        """Return the agent-select option with the given visible label."""
        return self._page.get_by_role("option", name=label, exact=True)
