from typing import Literal

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightDiffPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the diff panel.

    Wraps the panel's DOM region so tests can interact with tabs, the
    read-only preview, and inline diff views without holding raw test-id
    locators.
    """

    def get_tabs(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_TAB)

    def get_tab_by_name(self, tab_text: str) -> Locator:
        return self.get_tabs().filter(has_text=tab_text)

    def get_loading_bar(self) -> Locator:
        """The indeterminate progress bar shown while a diff fetch is in flight.

        Scoped to the diff panel so it never matches a progress indicator
        elsewhere in the app. The bar should only be present when a file is
        open and its diff is loading — never over the empty placeholder.
        """
        return self.get_by_role("progressbar")

    def close_tab(self, tab_text: str) -> None:
        """Close the tab labelled ``tab_text`` via its hover-revealed close button."""
        tab = self.get_tab_by_name(tab_text)
        expect(tab).to_be_visible()
        tab.hover()
        close_btn = tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
        expect(close_btn).to_be_visible()
        close_btn.click()

    def get_file_view_marker(self) -> Locator:
        """Hidden marker element rendered inside file-view tab labels.

        File-view, single-diff, combined-review, and commit-diff tabs all
        share the ``DIFF_TAB`` test id; the marker is what distinguishes a
        file-view tab from the others.
        """
        return self._page.get_by_test_id(ElementIDs.FILE_VIEW_TAB_MARKER)

    def get_file_header(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_FILE_HEADER)

    def get_read_only_preview(self) -> Locator:
        return self.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW)

    def get_file_sections(self) -> Locator:
        return self.get_by_test_id(ElementIDs.COMBINED_DIFF_FILE_SECTION)

    def get_scope_picker(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_PICKER)

    def get_scope_all(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_ALL)

    def get_scope_uncommitted(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_UNCOMMITTED)

    def get_expand_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_EXPAND_TOGGLE)

    def get_unified_diff_views(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_UNIFIED)

    def close_other_tabs_via_context_menu(self, tab_text: str) -> None:
        """Right-click a tab and select 'Close other tabs' from the context menu."""
        tab = self.get_tab_by_name(tab_text)
        expect(tab).to_be_visible()
        tab.click(button="right")
        close_others = self._page.get_by_test_id("close-other-tabs")
        expect(close_others).to_be_visible()
        close_others.click()

    def get_split_view_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SPLIT_VIEW_TOGGLE)

    def get_split_view(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_SPLIT)

    def get_line_wrap_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_LINE_WRAP_TOGGLE)

    def get_close_panel_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_CLOSE_PANEL_BUTTON)

    def get_render_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_RENDER_TOGGLE)

    def get_find_in_file_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_FIND_IN_FILE_BTN)

    def get_search_bar(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_IN_FILE_SEARCH_BAR)

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_IN_FILE_SEARCH_INPUT)

    def get_split_column_handle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SPLIT_COLUMN_HANDLE)

    def get_read_only_preview_markdown(self) -> Locator:
        return self.get_read_only_preview().get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)

    def get_read_only_preview_frontmatter(self) -> Locator:
        return self.get_read_only_preview_markdown().get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_FRONTMATTER)

    def ensure_render_mode(self, mode: Literal["rendered", "source"]) -> None:
        """Ensure the render-mode toggle is in ``mode`` (``"rendered"`` or ``"source"``)."""
        toggle = self.get_render_toggle()
        expect(toggle).to_be_visible()
        if toggle.get_attribute("data-state") != mode:
            toggle.click()
        expect(toggle).to_have_attribute("data-state", mode)

    def get_rename_banner(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_RENAME_BANNER)

    def get_file_header_menu_trigger(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_FILE_HEADER_MENU_TRIGGER)

    def get_copy_file_path_menu_item(self) -> Locator:
        return self._page.get_by_test_id("copy-path")

    def ensure_unified_mode(self) -> None:
        split_toggle = self.get_split_view_toggle()
        expect(split_toggle).to_be_visible()
        if split_toggle.get_attribute("data-state") == "split":
            split_toggle.click()
        expect(split_toggle).to_have_attribute("data-state", "unified")

    def ensure_split_mode(self) -> None:
        split_toggle = self.get_split_view_toggle()
        expect(split_toggle).to_be_visible()
        if split_toggle.get_attribute("data-state") != "split":
            split_toggle.click()
        expect(split_toggle).to_have_attribute("data-state", "split")

    def expect_shows_file_view(self, tab_text: str) -> None:
        """Assert a file-view tab with ``tab_text`` is open and rendering content."""
        expect(self).to_be_visible()
        tab = self.get_tab_by_name(tab_text)
        expect(tab.first).to_be_visible()
        file_view_tab = tab.filter(has=self.get_file_view_marker())
        expect(file_view_tab.first).to_be_visible()
        expect(self.get_read_only_preview()).to_be_visible()
        expect(self).not_to_contain_text("Could not load file content")


def get_diff_panel_from_page(page: Page) -> PlaywrightDiffPanelElement:
    locator = page.get_by_test_id(ElementIDs.DIFF_PANEL)
    return PlaywrightDiffPanelElement(locator=locator, page=page)
