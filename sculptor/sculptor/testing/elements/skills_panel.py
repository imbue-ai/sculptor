from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightSkillsPanelElement(PlaywrightIntegrationTestElement):
    """POM for the SkillsPanel side panel.

    Wraps the skill chip list, search toggle, and search input so test bodies
    don't reach into raw test ids.
    """

    def get_skill_chip(self, name: str) -> Locator:
        # The chip row renders the skill name as plain text; description lives
        # in a separate popover layer. has_text picks exactly the chip we want.
        return self.get_by_test_id(ElementIDs.SKILL_CHIP).filter(has_text=name)

    def get_search_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SKILLS_PANEL_SEARCH_TOGGLE)

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SKILLS_PANEL_SEARCH_INPUT)

    def open_search(self) -> Locator:
        """Click the search toggle and return the now-visible search input."""
        self.get_search_toggle().click()
        search_input = self.get_search_input()
        expect(search_input).to_be_visible()
        return search_input
