from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightFileTreeElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the file browser / file tree panel."""

    def get_tree_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW)

    def get_row_status(self, row: Locator) -> Locator:
        return row.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW_STATUS)


def get_file_tree(page: Page) -> PlaywrightFileTreeElement:
    locator = page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
    return PlaywrightFileTreeElement(locator=locator, page=page)


def get_changes_tree(page: Page) -> PlaywrightFileTreeElement:
    locator = page.get_by_test_id(ElementIDs.FILE_BROWSER_CHANGES_TREE)
    return PlaywrightFileTreeElement(locator=locator, page=page)
