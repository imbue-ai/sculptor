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


def get_file_browser_panel(page: Page) -> PlaywrightFileBrowserElement:
    locator = page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
    return PlaywrightFileBrowserElement(locator=locator, page=page)
