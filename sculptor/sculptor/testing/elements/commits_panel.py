from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.explorer_layout import PlaywrightExplorerLayoutElement
from sculptor.testing.elements.explorer_layout import get_explorer_layout_in


class PlaywrightCommitsPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Commits panel.

    The Commits panel pairs the commit history (graph terminus, commit rows,
    merge spur, per-commit popover with its file rows) with its own embedded
    DiffViewer via the shared ExplorerLayout. The list and viewer are siblings
    under the (untestid'd) ExplorerLayout row, so this POM is scoped to the owning
    SECTION root; the history list within it carries ``HISTORY_PANEL``.
    """

    def get_explorer_layout(self) -> PlaywrightExplorerLayoutElement:
        return get_explorer_layout_in(self, self._page)

    def get_diff_viewer(self) -> PlaywrightDiffViewerElement:
        return self.get_explorer_layout().get_diff_viewer()

    def get_list(self) -> Locator:
        """Get the commit-history list root (``HISTORY_PANEL``)."""
        return self.get_by_test_id(ElementIDs.HISTORY_PANEL)

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


def get_commits_panel_in(section_root: Locator, page: Page) -> PlaywrightCommitsPanelElement:
    """Return the Commits panel POM scoped to a section's root locator."""
    return PlaywrightCommitsPanelElement(locator=section_root, page=page)
