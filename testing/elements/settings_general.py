from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGeneralSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the General Settings section."""

    def select_default_model(self, model: str) -> None:
        """Select a default model from the dropdown."""
        self._get_default_model_select().click()
        options = self._page.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_MODEL_OPTION)
        found_option = None
        for option in options.all():
            if option.inner_text() == model:
                if found_option is not None:
                    raise ValueError(f"Multiple options found for model '{model}'")
                found_option = option
        if found_option is None:
            raise ValueError(f"Default model option '{model}' not found")
        found_option.click()

    def _get_default_model_select(self) -> Locator:
        """Get the default model select dropdown."""
        return self.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_MODEL_SELECT)
