from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.file_tree import PlaywrightFileTreeElement


class PlaywrightFileBrowserElement(PlaywrightIntegrationTestElement):
    """POM for the file browser panel."""

    def get_file_tree(self) -> PlaywrightFileTreeElement:
        locator = self.get_by_test_id(ElementIDs.FILE_BROWSER_FILE_TREE)
        return PlaywrightFileTreeElement(locator=locator, page=self._page)

    def get_tree_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW)

    def get_changes_tree(self) -> PlaywrightFileTreeElement:
        locator = self.get_by_test_id(ElementIDs.FILE_BROWSER_CHANGES_TREE)
        return PlaywrightFileTreeElement(locator=locator, page=self._page)

    def get_history_panel(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.HISTORY_PANEL)

    def get_search_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_SEARCH_FILES_BTN)

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_SEARCH_INPUT)

    def get_search_close(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_SEARCH_CLOSE)

    def get_collapse_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_COLLAPSE_FOLDERS_BTN)

    def get_refresh_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_REFRESH_BTN)

    def get_status_indicators(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW_STATUS)

    def get_review_all_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHANGES_REVIEW_ALL_BTN)


def get_file_browser_panel(page: Page) -> PlaywrightFileBrowserElement:
    locator = page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
    return PlaywrightFileBrowserElement(locator=locator, page=page)
