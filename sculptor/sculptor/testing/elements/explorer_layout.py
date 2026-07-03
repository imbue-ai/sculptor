from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.diff_viewer import get_diff_viewer_in

# Budget for wait_for_list_width_above's post-drag settle poll: a busy renderer
# can commit the resized layout a beat after the pointer-up round-trip returns.
_LIST_WIDTH_POLL_ATTEMPTS = 50
_LIST_WIDTH_POLL_INTERVAL_MS = 100


class PlaywrightExplorerLayoutElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the shared list-plus-viewer scaffold.

    The Files / Changes / Commits panels embed the same ``ExplorerLayout``: a
    list (file tree / changes browser / commit history) on the left and an
    always-visible viewer on the right, separated by a drag-resizable divider.
    The list width is one persisted value shared across the three panels and
    across workspaces (clamped to a min/max in the atom), so resizing it in one
    panel resizes it everywhere. The sidebar-visibility toggle is rendered into
    the viewer's header; when nothing is selected the viewer shows its empty
    state.

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
        """The drag-resizable divider between the list and the viewer.

        A ``role=separator`` element labeled distinctly from the workspace
        sidebar's handle (which lives outside the section scope anyway) and
        from a split section's ``Resize {section} split`` divider, so it
        resolves uniquely within the section. Hidden while the sidebar is
        collapsed.
        """
        return self.get_by_role("separator", name="Resize file list")

    def get_list_width_px(self) -> float:
        """Measure the rendered width of the list pane, in pixels.

        The resize divider sits immediately after the list pane and the pane
        starts at the section root's left edge, so the distance between their
        x-positions is the pane's rendered width. Measuring via the divider is
        uniform across the Files / Changes / Commits lists, whose content
        carries different testids.
        """
        handle_box = self.get_resize_handle().bounding_box()
        root_box = self.bounding_box()
        assert handle_box is not None and root_box is not None, "list pane and divider must be visible to measure"
        return handle_box["x"] - root_box["x"]

    def wait_for_list_width_above(self, min_px: float) -> float:
        """Poll the rendered list width until it exceeds ``min_px``; return it.

        A divider drag writes the new width synchronously during the pointer
        moves, but a busy renderer can commit the resulting layout a beat
        after the pointer-up round-trip returns, so a single post-drag
        measurement can still read the pre-drag layout. Polling keeps the
        measurement robust under load; a width that never crosses ``min_px``
        raises with both values so direction-of-change failures stay readable.
        """
        width = 0.0
        for _attempt in range(_LIST_WIDTH_POLL_ATTEMPTS):
            width = self.get_list_width_px()
            if width > min_px:
                return width
            self._page.wait_for_timeout(_LIST_WIDTH_POLL_INTERVAL_MS)
        raise AssertionError(f"List pane width never exceeded {min_px:.0f}px; last measured {width:.0f}px")

    def drag_resize_handle_by(self, delta_px: float) -> None:
        """Drag the list divider horizontally by ``delta_px`` (positive widens the list).

        Uses raw mouse down / stepped move / up because the handle listens for
        window-level pointer events during the drag (it is not HTML
        drag-and-drop, so ``drag_to`` does not apply).
        """
        handle = self.get_resize_handle()
        expect(handle).to_be_visible()
        box = handle.bounding_box()
        assert box is not None
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        self._page.mouse.move(start_x, start_y)
        self._page.mouse.down()
        self._page.mouse.move(start_x + delta_px, start_y, steps=5)
        self._page.mouse.up()

    def get_diff_viewer(self) -> PlaywrightDiffViewerElement:
        """Get the viewer (detail) embedded in this layout."""
        return get_diff_viewer_in(self, self._page)

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

    Selects the tree row whose name label is exactly the basename of ``file_path``
    (the tree shows basenames) within the section, then returns the embedded viewer
    so callers can assert the diff. Exact-matching the name label keeps a basename
    that is a substring of another row's (e.g. ``foo.py`` vs ``test_foo.py``) from
    resolving to the wrong row. Works for Files / Changes / Commits since they all
    share the ExplorerLayout shape with a ``FILE_BROWSER_TREE_ROW`` list.
    """
    layout = get_explorer_layout_in(section_root, page)
    basename = file_path.split("/")[-1]
    row = layout.get_tree_rows().filter(has=page.get_by_text(basename, exact=True))
    expect(row.first).to_be_visible()
    row.first.click()
    return layout.get_diff_viewer()
