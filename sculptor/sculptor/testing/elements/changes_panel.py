from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.explorer_layout import PlaywrightExplorerLayoutElement
from sculptor.testing.elements.explorer_layout import get_explorer_layout_in
from sculptor.testing.elements.explorer_layout import open_file_in_panel
from sculptor.testing.elements.file_tree import PlaywrightFileTreeElement


class PlaywrightChangesPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Changes panel.

    The Changes panel pairs the changes browser (scope picker All/Uncommitted +
    commit button + changed-file tree + discard) with its own embedded DiffViewer
    via the shared ExplorerLayout. The list and viewer are siblings under the
    (untestid'd) ExplorerLayout row, so this POM is scoped to the owning SECTION
    root; the changes browser list within it carries ``CHANGES_PANEL``.
    """

    def get_explorer_layout(self) -> PlaywrightExplorerLayoutElement:
        return get_explorer_layout_in(self, self._page)

    def get_diff_viewer(self) -> PlaywrightDiffViewerElement:
        return self.get_explorer_layout().get_diff_viewer()

    def get_list(self) -> Locator:
        """Get the changes-browser list root (``CHANGES_PANEL``)."""
        return self.get_by_test_id(ElementIDs.CHANGES_PANEL)

    def get_scope_picker(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_PICKER)

    def get_scope_all(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_ALL)

    def get_scope_uncommitted(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_UNCOMMITTED)

    def get_commit_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHANGES_COMMIT_BUTTON)

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

    def open_file(self, file_path: str) -> PlaywrightDiffViewerElement:
        """Click a changed-file row and return the panel's embedded viewer."""
        return open_file_in_panel(self, self._page, file_path)


def get_changes_panel_in(section_root: Locator, page: Page) -> PlaywrightChangesPanelElement:
    """Return the Changes panel POM scoped to a section's root locator."""
    return PlaywrightChangesPanelElement(locator=section_root, page=page)
