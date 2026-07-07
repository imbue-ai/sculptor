from typing import Literal

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.base import open_radix_toggle

MenuOption = Literal["find_in_file", "split_view", "line_wrap", "render", "tree_view_mode", "collapse_all"]

# The view options that live in the viewer's triple-dot menu. Each maps
# to the testid of its menu item so ``toggle_view_option_via_menu`` can open the
# menu once and click the right row regardless of which option a test wants.
_MENU_OPTION_TEST_IDS: dict[MenuOption, ElementIDs] = {
    "find_in_file": ElementIDs.DIFF_FIND_IN_FILE_BTN,
    "split_view": ElementIDs.DIFF_SPLIT_VIEW_TOGGLE,
    "line_wrap": ElementIDs.DIFF_LINE_WRAP_TOGGLE,
    "render": ElementIDs.DIFF_RENDER_TOGGLE,
    "tree_view_mode": ElementIDs.DIFF_MENU_TREE_VIEW_MODE,
    "collapse_all": ElementIDs.FILE_BROWSER_COLLAPSE_FOLDERS_BTN,
}


class PlaywrightDiffViewerElement(PlaywrightIntegrationTestElement):
    """Page Object Model for an embeddable per-panel diff/file viewer.

    Each Files / Changes / Commits panel embeds its OWN viewer instance with its
    own selection — there is no shared "active diff" singleton — so this POM is
    constructed scoped to a single panel's viewer rather than reaching for a
    page-wide diff panel. All view toggles (split/unified, line wrap,
    find-in-file, render markdown) and the list flat/tree + collapse-all controls
    live in the header's single triple-dot menu
    (``DIFF_FILE_HEADER_MENU_TRIGGER``); reach them through
    ``toggle_view_option_via_menu``. There is no expand/fullscreen control;
    section maximize handles full-screening instead.
    """

    def get_file_header(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_FILE_HEADER)

    def get_read_only_preview(self) -> Locator:
        return self.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW)

    def get_read_only_preview_markdown(self) -> Locator:
        return self.get_read_only_preview().get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)

    def get_read_only_preview_frontmatter(self) -> Locator:
        """The frontmatter metadata table inside the rendered markdown body.

        ``ReadOnlyPreview`` strips a leading frontmatter block off the markdown
        and renders it as a styled table nested inside
        ``READ_ONLY_PREVIEW_MARKDOWN``, so scoping through the markdown wrapper
        also pins that the block is a rendered-view-only affordance.
        """
        return self.get_read_only_preview_markdown().get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_FRONTMATTER)

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

        The trigger is a Radix menu, so opening is idempotent and retried (see
        ``open_radix_toggle``).
        """
        open_radix_toggle(self._page, self.get_menu_trigger())

    def get_menu_option(self, option: MenuOption) -> Locator:
        """Get a menu item by its logical option name.

        The menu renders in a Radix portal, so its items are located page-wide
        rather than scoped to this viewer's header.
        """
        return self._page.get_by_test_id(_MENU_OPTION_TEST_IDS[option])

    def toggle_view_option_via_menu(self, option: MenuOption) -> None:
        """Open the triple-dot menu and click the ``option`` toggle.

        Covers the diff view toggles (find-in-file, split/unified, line wrap,
        render markdown) and the list controls (flat/tree, collapse-all), which
        all live under ``DIFF_FILE_HEADER_MENU_TRIGGER``.
        """
        self.open_menu()
        item = self.get_menu_option(option)
        expect(item).to_be_visible()
        item.click()

    # -- The recent-files dropdown on the header file path --

    def get_file_path_select(self) -> Locator:
        """The header's file-path breadcrumb, which doubles as the
        recently-viewed-files dropdown trigger."""
        return self.get_file_header().get_by_test_id(ElementIDs.DIFF_FILE_PATH_SELECT)

    def open_recent_files_dropdown(self) -> None:
        """Open the header path's recently-viewed-files dropdown.

        The trigger is a Radix Select, so opening is idempotent and retried (see
        ``open_radix_toggle``).
        """
        open_radix_toggle(self._page, self.get_file_path_select())

    def get_recent_file_options(self) -> Locator:
        """All options in the open recent-files dropdown.

        The dropdown renders in a Radix portal, so options are located
        page-wide by their ARIA role rather than scoped to this viewer.
        """
        return self._page.get_by_role("option")

    def close_recent_files_dropdown(self) -> None:
        """Close the recent-files dropdown without selecting an option."""
        self._page.keyboard.press("Escape")
        expect(self.get_file_path_select()).not_to_have_attribute("data-state", "open")

    def select_recent_file(self, file_name: str) -> None:
        """Open the recent-files dropdown and pick the option for ``file_name``.

        Matches the option whose file-name label is exactly ``file_name`` so a
        recent whose name is a substring of another's (e.g. ``util.py`` vs
        ``test_util.py``) never resolves to two options.
        """
        self.open_recent_files_dropdown()
        option = self.get_recent_file_options().filter(has=self._page.get_by_text(file_name, exact=True))
        expect(option).to_be_visible()
        option.click()

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


def ensure_unified_view(viewer: PlaywrightDiffViewerElement) -> None:
    """Drive the viewer into unified mode so the unified diff body can be asserted.

    The split/unified preference is a server-persisted config, so a prior test in
    the same browser context can leave it on either view. The split/unified toggle
    is a plain menu Item (not a checkbox), so the effective view is read from
    CONTENT — which of ``DIFF_VIEW_UNIFIED`` / ``DIFF_VIEW_SPLIT`` is mounted — and
    the toggle is clicked only when the split view is the one showing. Idempotent.
    (Added/deleted files always render unified regardless.)
    """
    unified = viewer.get_unified_diff_views()
    split = viewer.get_split_view()
    expect(unified.or_(split)).to_be_visible()
    if split.count() > 0:
        viewer.toggle_view_option_via_menu("split_view")
    expect(viewer.get_unified_diff_views()).to_be_visible()


def wait_for_full_content_diff_render(page: Page, last_hunk_text: str) -> None:
    """Block until Pierre's full-content render pass paints through ``last_hunk_text``.

    Pierre paints the diff twice: first straight from the diff string (a
    *partial* diff), then again once ``useFileLines`` resolves and the full
    old/new file lines reach Pierre — the pass whose hunk rows are looked up
    by index in those arrays, and the pass where an out-of-range index (a
    too-short old/new lines array) makes ``DiffHunksRenderer`` throw. Only a
    non-partial diff marks its hunk separators expandable, so a separator
    carrying ``data-expand-index`` is the signature of that second pass. Its
    rows then stream in as Shiki tokenises, so additionally wait for the
    ``div[data-line]`` carrying ``last_hunk_text`` — pass text from the diff's
    LAST hunk so every hunk's line-array lookups have run by the time this
    returns.

    The ``<diffs-container>`` custom element and its shadow root are the same
    in unified and split view, so this matches either ``DIFF_VIEW_UNIFIED`` or
    ``DIFF_VIEW_SPLIT`` and does not require forcing a particular view first.
    The shadow root is pierced manually because these are Pierre attributes
    with no Playwright locator equivalent.

    The combined "Review all" view mounts ONE such diff view per changed file,
    so every ``DIFF_VIEW_*`` on the page is scanned and a SINGLE view must carry
    both the expandable separator and ``last_hunk_text`` — the signature of the
    one file whose full-content pass this call is gating. Matching the separator
    on one file and the text on another would return too early, so both must be
    found in the same shadow root. The single-file diff panel mounts exactly one
    view, so this collapses to that view there.
    """
    page.wait_for_function(
        """({ unifiedTestid, splitTestid, text }) => {
            const views = document.querySelectorAll(
                `[data-testid="${unifiedTestid}"], [data-testid="${splitTestid}"]`
            );
            return [...views].some((view) => {
                const shadow = view.querySelector("diffs-container")?.shadowRoot;
                if (!shadow?.querySelector("[data-separator][data-expand-index]")) return false;
                return [...shadow.querySelectorAll("div[data-line]")].some(
                    (line) => line.textContent.includes(text)
                );
            });
        }""",
        arg={
            "unifiedTestid": ElementIDs.DIFF_VIEW_UNIFIED,
            "splitTestid": ElementIDs.DIFF_VIEW_SPLIT,
            "text": last_hunk_text,
        },
    )
