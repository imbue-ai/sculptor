from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.file_tree import PlaywrightFileTreeElement


class PlaywrightChangesPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the changes panel (scope picker + file tree)."""

    def get_scope_picker(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_PICKER)

    def get_scope_all(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_ALL)

    def get_scope_uncommitted(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_UNCOMMITTED)

    def get_changes_tree(self) -> PlaywrightFileTreeElement:
        tree_locator = self.get_by_test_id(ElementIDs.FILE_BROWSER_CHANGES_TREE)
        return PlaywrightFileTreeElement(locator=tree_locator, page=self._page)

    def get_discard_button(self, row: Locator) -> Locator:
        return row.get_by_test_id(ElementIDs.DISCARD_BUTTON)

    def get_discard_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DISCARD_DIALOG)

    def get_discard_dialog_confirm(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DISCARD_DIALOG_CONFIRM)

    def get_discard_dialog_cancel(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DISCARD_DIALOG_CANCEL)
