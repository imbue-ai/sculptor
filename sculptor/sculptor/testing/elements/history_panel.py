from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightHistoryPanelElement(PlaywrightIntegrationTestElement):
    """POM for the history panel within the file browser."""

    def get_terminus(self) -> Locator:
        return self.get_by_test_id(ElementIDs.HISTORY_TERMINUS)

    def get_commit_entries(self) -> Locator:
        return self.get_by_test_id(ElementIDs.HISTORY_COMMIT_ENTRY)

    def get_commit_entry_by_text(self, text: str) -> Locator:
        return self.get_commit_entries().filter(has_text=text)

    def get_commit_message(self, entry: Locator) -> Locator:
        return entry.get_by_test_id(ElementIDs.HISTORY_COMMIT_MESSAGE)

    def get_commit_meta(self, entry: Locator) -> Locator:
        return entry.get_by_test_id(ElementIDs.HISTORY_COMMIT_META)

    def get_merge_spur(self) -> Locator:
        return self.get_by_test_id(ElementIDs.HISTORY_MERGE_SPUR)

    def get_commit_popover(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.HISTORY_COMMIT_POPOVER)

    def get_tree_rows(self, entry: Locator) -> Locator:
        return entry.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW)


def get_history_panel(page: Page) -> PlaywrightHistoryPanelElement:
    locator = page.get_by_test_id(ElementIDs.HISTORY_PANEL)
    return PlaywrightHistoryPanelElement(locator=locator, page=page)
