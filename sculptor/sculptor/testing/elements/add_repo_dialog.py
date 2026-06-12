from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightAddRepoDialogElement(PlaywrightIntegrationTestElement):
    def get_path_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_PATH_INPUT)

    def get_path_autocomplete_items(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PATH_AUTOCOMPLETE_ITEM)

    def get_submit_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_SUBMIT_BUTTON)

    def get_submit_hint(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PATH_AUTOCOMPLETE_SUBMIT_HINT)
