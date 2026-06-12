from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightAgentSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Agent Settings section."""

    def get_model_select(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_MODEL_SELECT)

    def get_fast_mode_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_FAST_MODE_TOGGLE)

    def get_effort_level_select(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_EFFORT_LEVEL_SELECT)

    def select_effort_level(self, text: str) -> None:
        self.get_effort_level_select().click()
        options = self._page.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_EFFORT_LEVEL_OPTION)
        target = options.filter(has=self._page.get_by_text(text, exact=True))
        expect(target).to_be_visible()
        target.click()
