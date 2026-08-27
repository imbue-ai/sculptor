from typing import Literal

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightDiffPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the single embedded diff/file viewer.

    The section shell renders ONE embedded ``DiffViewer`` per host panel
    (Files / Changes / Commits) — there is no multi-file tab bar. This POM
    wraps that single viewer's DOM region (``DIFF_PANEL``) so tests can read
    the open file's header, read-only preview, and inline diff views without
    holding raw test-id locators.
    """

    def get_loading_bar(self) -> Locator:
        """The indeterminate progress bar shown while a diff fetch is in flight.

        Scoped to the diff panel so it never matches a progress indicator
        elsewhere in the app. The bar should only be present when a file is
        open and its diff is loading — never over the empty placeholder.
        """
        return self.get_by_role("progressbar")

    def get_file_header(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_FILE_HEADER)

    def get_read_only_preview(self) -> Locator:
        return self.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW)

    def get_unified_diff_views(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_UNIFIED)

    def get_split_view(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_SPLIT)

    def get_line_wrap_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_LINE_WRAP_TOGGLE)

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

    def expect_shows_file(self, file_name: str) -> None:
        """Assert the single viewer is open and rendering ``file_name``'s content.

        The single embedded viewer shows one file at a time. A file is "open"
        when the viewer is visible, its header breadcrumb shows the basename,
        and the read-only preview renders the content (without a load error).
        """
        expect(self).to_be_visible()
        expect(self.get_file_header()).to_contain_text(file_name)
        expect(self.get_read_only_preview()).to_be_visible()
        expect(self).not_to_contain_text("Could not load file content")


def get_diff_panel_from_page(page: Page) -> PlaywrightDiffPanelElement:
    locator = page.get_by_test_id(ElementIDs.DIFF_PANEL)
    return PlaywrightDiffPanelElement(locator=locator, page=page)
