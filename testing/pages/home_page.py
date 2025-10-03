from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.task_starter import PlaywrightTaskStarterElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightHomePage(PlaywrightProjectLayoutPage):
    def get_task_starter(self) -> PlaywrightTaskStarterElement:
        task_starter = self.get_by_test_id(ElementIDs.TASK_STARTER)
        return PlaywrightTaskStarterElement(locator=task_starter, page=self._page)

    def get_version_element(self) -> Locator:
        """Get the version element at the bottom of the page."""
        version_element = self.get_by_test_id(ElementIDs.VERSION)
        return version_element

    def get_repository_indicator(self) -> Locator:
        return self.get_by_test_id(ElementIDs.REPO_INDICATOR)
