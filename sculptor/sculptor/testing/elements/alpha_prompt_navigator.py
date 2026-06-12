from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

ALPHA_DOT_RAIL = "ALPHA_PROMPT_NAVIGATOR_RAIL"
ALPHA_DOT = "ALPHA_PROMPT_NAVIGATOR_DOT"
ALPHA_TOOLTIP = "ALPHA_PROMPT_NAVIGATOR_TOOLTIP"
ALPHA_COLLAPSED = "ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR"
ALPHA_COPY_BUTTON = "ALPHA_PROMPT_NAVIGATOR_COPY_BUTTON"


class PlaywrightAlphaPromptNavigatorElement(PlaywrightIntegrationTestElement):
    """POM for the alpha prompt navigator dot rail."""

    def get_dots(self) -> Locator:
        return self.get_by_test_id(ALPHA_DOT)

    def get_dot(self, index: int) -> Locator:
        return self.get_dots().nth(index)

    def get_tooltip(self) -> Locator:
        return self._page.get_by_test_id(ALPHA_TOOLTIP)

    def get_copy_button(self) -> Locator:
        return self.get_tooltip().get_by_test_id(ALPHA_COPY_BUTTON)


def get_alpha_prompt_navigator(page: Page) -> PlaywrightAlphaPromptNavigatorElement:
    locator = page.get_by_test_id(ALPHA_DOT_RAIL)
    return PlaywrightAlphaPromptNavigatorElement(locator=locator, page=page)
