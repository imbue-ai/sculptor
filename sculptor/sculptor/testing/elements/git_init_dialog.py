from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGitInitDialogElement(PlaywrightIntegrationTestElement):
    def get_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PROJECT_GIT_INIT_CONFIRM)

    def get_initial_commit_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PROJECT_INITIAL_COMMIT_CONFIRM)
