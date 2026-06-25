from typing import Literal

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# The view options that live in the viewer's triple-dot menu. Each maps
# to the testid of its menu item so ``toggle_view_option_via_menu`` can open the
# menu once and click the right row regardless of which option a test wants.
_MENU_OPTION_TEST_IDS: dict[str, ElementIDs] = {
    "find_in_file": ElementIDs.DIFF_FIND_IN_FILE_BTN,
    "split_view": ElementIDs.DIFF_SPLIT_VIEW_TOGGLE,
    "line_wrap": ElementIDs.DIFF_LINE_WRAP_TOGGLE,
    "render": ElementIDs.DIFF_RENDER_TOGGLE,
    "tree_view_mode": ElementIDs.DIFF_MENU_TREE_VIEW_MODE,
    "collapse_all": ElementIDs.FILE_BROWSER_COLLAPSE_FOLDERS_BTN,
}

MenuOption = Literal["find_in_file", "split_view", "line_wrap", "render", "tree_view_mode", "collapse_all"]


class PlaywrightDiffViewerElement(PlaywrightIntegrationTestElement):
    """Page Object Model for an embeddable per-panel diff/file viewer.

    Each Files / Changes / Commits panel embeds its OWN viewer instance with its
    own selection — there is no shared "active diff" singleton — so this POM is
    constructed scoped to a single panel's viewer rather than reaching for a
    page-wide diff panel. The view toggles that used to be toolbar icons
    (split/unified, line wrap, find-in-file, render markdown) and the list
    flat/tree + collapse-all controls now hang off the header's single triple-dot
    menu (``DIFF_FILE_HEADER_MENU_TRIGGER``); reach them through
    ``toggle_view_option_via_menu``. There is no expand/fullscreen control — the
    diff-specific fullscreen is deprecated in favour of section maximize.
    """

    def get_file_header(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_FILE_HEADER)

    def get_read_only_preview(self) -> Locator:
        return self.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW)

    def get_read_only_preview_markdown(self) -> Locator:
        return self.get_read_only_preview().get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)

    def get_skeleton(self) -> Locator:
        """The static, no-shimmer placeholder shown while a diff is about to render."""
        return self.get_by_test_id(ElementIDs.DIFF_SKELETON)

    def get_empty_body(self) -> Locator:
        """The empty placeholder shown when no file is selected."""
        return self.get_by_test_id(ElementIDs.DIFF_VIEWER_EMPTY)

    def get_loading_bar(self) -> Locator:
        """The indeterminate progress bar shown while a diff fetch is in flight.

        Scoped to this viewer so it never matches a progress indicator elsewhere
        in the app. The bar only appears when a file is open and its diff is
        loading — never over the empty placeholder.
        """
        return self.get_by_role("progressbar")

    def get_unified_diff_views(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_UNIFIED)

    def get_split_view(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_SPLIT)

    def get_split_column_handle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SPLIT_COLUMN_HANDLE)

    def get_rename_banner(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_RENAME_BANNER)

    def get_file_sections(self) -> Locator:
        return self.get_by_test_id(ElementIDs.COMBINED_DIFF_FILE_SECTION)

    def get_search_bar(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_IN_FILE_SEARCH_BAR)

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_IN_FILE_SEARCH_INPUT)

    # -- The triple-dot menu --

    def get_menu_trigger(self) -> Locator:
        return self.get_file_header().get_by_test_id(ElementIDs.DIFF_FILE_HEADER_MENU_TRIGGER)

    def open_menu(self) -> None:
        """Open the header's triple-dot options menu.

        Idempotent and verified: a Radix trigger toggles, so clicking one that is
        already open would close it. Gate on the trigger's ``data-state`` and wait
        until it is actually open, so repeated open/read/close cycles (e.g. flipping
        a checkbox item then re-reading) are reliable.
        """
        trigger = self.get_menu_trigger()
        expect(trigger).to_be_visible()
        # Radix can swallow the trigger click in the brief settle window right after
        # a previous close, so retry until the menu actually opens.
        for _ in range(5):
            if trigger.get_attribute("data-state") == "open":
                return
            trigger.click()
            try:
                expect(trigger).to_have_attribute("data-state", "open", timeout=2_000)
                return
            except AssertionError:
                self._page.wait_for_timeout(250)
        expect(trigger).to_have_attribute("data-state", "open")

    def get_menu_option(self, option: MenuOption) -> Locator:
        """Get a menu item by its logical option name.

        The menu renders in a Radix portal, so its items are located page-wide
        rather than scoped to this viewer's header.
        """
        return self._page.get_by_test_id(_MENU_OPTION_TEST_IDS[option])

    def toggle_view_option_via_menu(self, option: MenuOption) -> None:
        """Open the triple-dot menu and click the relocated ``option`` toggle.

        Covers the diff view toggles (find-in-file, split/unified, line wrap,
        render markdown) and the list controls (flat/tree, collapse-all) that all
        re-anchored under ``DIFF_FILE_HEADER_MENU_TRIGGER``.
        """
        self.open_menu()
        item = self.get_menu_option(option)
        expect(item).to_be_visible()
        item.click()

    # -- The sidebar-visibility toggle --

    def get_hide_sidebar_button(self) -> Locator:
        """The sidebar toggle while the list is visible ("Hide sidebar")."""
        return self.get_file_header().get_by_test_id(ElementIDs.FILE_BROWSER_HIDE_TREE_BTN)

    def get_show_sidebar_button(self) -> Locator:
        """The sidebar toggle while the list is collapsed ("Show sidebar")."""
        return self.get_file_header().get_by_test_id(ElementIDs.DIFF_HEADER_SHOW_TREE_BTN)

    # -- Assertions --

    def assert_diff_shows(self, file_path: str) -> None:
        """Assert the viewer header is showing the diff/file for ``file_path``.

        The header renders the path as a breadcrumb (dir segments + file name),
        so the basename is asserted against the header text. Also guards against
        the load-failure placeholder leaking through.
        """
        expect(self).to_be_visible()
        header = self.get_file_header()
        expect(header).to_be_visible()
        expect(header).to_contain_text(file_path.split("/")[-1])
        expect(self).not_to_contain_text("Could not load file content")


def get_diff_viewer_in(panel: Locator, page: Page) -> PlaywrightDiffViewerElement:
    """Return the diff viewer embedded inside a panel's root locator.

    Files / Changes / Commits each embed their own viewer, so the viewer is
    resolved relative to the owning panel's root rather than page-wide.
    """
    locator = panel.get_by_test_id(ElementIDs.DIFF_PANEL)
    return PlaywrightDiffViewerElement(locator=locator, page=page)
