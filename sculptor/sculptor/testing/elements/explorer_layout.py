from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.diff_viewer import get_diff_viewer_in


class PlaywrightExplorerLayoutElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the shared list-plus-viewer scaffold.

    The Files / Changes / Commits panels embed the same ``ExplorerLayout``: a
    fixed-width list (file tree / changes browser / commit history) on the
    left — not user-resizable, so the pane stays the same size across panels —
    and an always-visible viewer on the right. The sidebar-visibility toggle is
    rendered into the viewer's header; when nothing is selected the
    viewer shows its empty state.

    The layout's row container carries no testid and the list / viewer are
    SIBLINGS under it, so this POM is constructed scoped to the owning SECTION
    root (``SECTION_LEFT`` etc.). A section hosts one active panel, so the list
    and viewer resolve uniquely within it.
    """

    def get_list(self) -> Locator:
        """Get the Files panel's master list (the file tree).

        The Changes / Commits lists carry their own root testids
        (``CHANGES_PANEL`` / none), so their panel POMs override list access;
        this default targets the Files panel's ``FILE_BROWSER_PANEL`` list.
        """
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)

    def get_resize_handle(self) -> Locator:
        """The list-resize divider the fixed-width redesign REMOVED.

        The layout intentionally renders no such separator anymore; this
        locator exists so tests can assert the affordance stays gone
        (``to_have_count(0)``). The workspace sidebar's identically named
        handle lives outside the section scope, so it cannot match here.
        """
        return self.get_by_role("separator", name="Resize sidebar")

    def get_diff_viewer(self) -> PlaywrightDiffViewerElement:
        """Get the viewer (detail) embedded in this layout."""
        return get_diff_viewer_in(self, self._page)

    def get_empty_detail(self) -> Locator:
        """The always-rendered viewer body, which shows its empty placeholder
        text when nothing is selected."""
        return self.get_diff_viewer()

    def get_tree_rows(self) -> Locator:
        """Get the list's tree rows (file / changed-file / per-commit file rows).

        Rows render only in the list, never in the viewer, so they resolve
        uniquely within the section without scoping to a list-specific root.
        """
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW)

    def get_hide_sidebar_button(self) -> Locator:
        """The sidebar-visibility toggle while the list is visible ("Hide sidebar")."""
        return self.get_by_test_id(ElementIDs.FILE_BROWSER_HIDE_TREE_BTN)

    def get_show_sidebar_button(self) -> Locator:
        """The sidebar-visibility toggle while the list is collapsed ("Show sidebar")."""
        return self.get_by_test_id(ElementIDs.DIFF_HEADER_SHOW_TREE_BTN)

    def hide_sidebar(self) -> None:
        """Collapse the list so only the viewer remains."""
        toggle = self.get_hide_sidebar_button()
        expect(toggle).to_be_visible()
        toggle.click()

    def show_sidebar(self) -> None:
        """Re-expand a collapsed list."""
        toggle = self.get_show_sidebar_button()
        expect(toggle).to_be_visible()
        toggle.click()


def get_explorer_layout_in(section_root: Locator, page: Page) -> PlaywrightExplorerLayoutElement:
    """Return the ExplorerLayout scaffold scoped to a section's root locator."""
    return PlaywrightExplorerLayoutElement(locator=section_root, page=page)


def open_file_in_panel(section_root: Locator, page: Page, file_path: str) -> PlaywrightDiffViewerElement:
    """Click a file row in a panel's list and return the panel's diff viewer.

    Selects the tree row whose text matches the basename of ``file_path`` (the
    tree shows basenames) within the section, then returns the embedded viewer so
    callers can assert the diff. Works for Files / Changes / Commits since they
    all share the ExplorerLayout shape with a ``FILE_BROWSER_TREE_ROW`` list.
    """
    layout = get_explorer_layout_in(section_root, page)
    row = layout.get_tree_rows().filter(has_text=file_path.split("/")[-1])
    expect(row.first).to_be_visible()
    row.first.click()
    return layout.get_diff_viewer()
