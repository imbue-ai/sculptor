from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.explorer_layout import PlaywrightExplorerLayoutElement
from sculptor.testing.elements.explorer_layout import get_explorer_layout_in
from sculptor.testing.elements.explorer_layout import open_file_in_panel
from sculptor.testing.elements.file_tree import PlaywrightFileTreeElement


class PlaywrightFilesPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Files panel.

    The Files panel pairs the workspace file tree (the list) with its own
    embedded DiffViewer (the detail) via the shared ExplorerLayout. There are no
    All/Changes/History tabs — those became the separate Changes and Commits
    panels — so this POM exposes the file tree, the search box, and helpers to
    open a file into the embedded viewer.

    The list and viewer are siblings under the (untestid'd) ExplorerLayout row,
    so this POM is scoped to the owning SECTION root; the file-tree list within
    it carries ``FILE_BROWSER_PANEL``.
    """

    def get_explorer_layout(self) -> PlaywrightExplorerLayoutElement:
        return get_explorer_layout_in(self, self._page)

    def get_diff_viewer(self) -> PlaywrightDiffViewerElement:
        return self.get_explorer_layout().get_diff_viewer()

    def get_list(self) -> Locator:
        """Get the file-tree list root (``FILE_BROWSER_PANEL``)."""
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)

    def get_file_tree(self) -> PlaywrightFileTreeElement:
        locator = self.get_by_test_id(ElementIDs.FILE_BROWSER_FILE_TREE)
        return PlaywrightFileTreeElement(locator=locator, page=self._page)

    def get_tree_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW)

    def get_scrollbar_thumb(self) -> Locator:
        """Get the file tree's overlay scrollbar thumb."""
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_SCROLLBAR_THUMB)

    def get_status_indicators(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW_STATUS)

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_SEARCH_INPUT)

    def get_empty_state(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_EMPTY)

    def get_skeleton(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_SKELETON)

    def open_file(self, file_path: str) -> PlaywrightDiffViewerElement:
        """Click a file row and return the panel's embedded viewer."""
        return open_file_in_panel(self, self._page, file_path)


def get_files_panel_in(section_root: Locator, page: Page) -> PlaywrightFilesPanelElement:
    """Return the Files panel POM scoped to a section's root locator."""
    return PlaywrightFilesPanelElement(locator=section_root, page=page)
