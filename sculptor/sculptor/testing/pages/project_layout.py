from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.elements.command_palette import PlaywrightCommandPaletteElement
from sculptor.testing.elements.git_init_dialog import PlaywrightGitInitDialogElement
from sculptor.testing.elements.keyboard_shortcuts_dialog import PlaywrightKeyboardShortcutsDialogElement
from sculptor.testing.elements.project_path_dialog import PlaywrightProjectPathDialogElement
from sculptor.testing.elements.skills_panel import PlaywrightSkillsPanelElement
from sculptor.testing.elements.warning_banner import PlaywrightWarningBannerElement
from sculptor.testing.elements.workspace_peek import PlaywrightWorkspacePeekElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.elements.workspace_sidebar import PlaywrightWorkspaceSidebarElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage
from sculptor.testing.utils import get_playwright_modifier_key


class PlaywrightProjectLayoutPage(PlaywrightIntegrationTestPage):
    """Page object for the workspace shell — the sidebar + section grid.

    This is the UI-refresh shim (Task 2.7): the old top-bar/tab API has been
    replaced by a sidebar + section API while the cross-cutting survivors
    (keyboard shortcuts, command palette, warning banner, the git-init /
    add-repo / project-path / keyboard-shortcuts dialogs) keep their original
    method signatures so the content-only majority of tests keep passing.

    The old tab getters (``get_home_tab``, the ``get_tab_context_menu_*`` set,
    ``get_topbar``, ``get_bottom_bar``, …) targeted surfaces that no longer
    render on the workspace route; the tests that drove them are deleted in
    Phase 8. Use ``get_workspace_sidebar()`` for navigation and ``get_section()``
    for the panel grid. ``get_workspace_tabs`` survives below as a thin shim onto
    the sidebar rows for the regression / real_pi suites that were not swept.
    """

    # -- Sidebar + sections (the new layout spine) --

    def get_workspace_sidebar(self) -> PlaywrightWorkspaceSidebarElement:
        """Get the workspace navigation sidebar POM (SIDE-*)."""
        return get_workspace_sidebar(self._page)

    def get_workspace_peek_popover(self) -> PlaywrightWorkspacePeekElement:
        """Get the workspace peek popover POM (visible only while hovering a sidebar row).

        The peek follows the hovered workspace **row** in the sidebar (it used to
        follow the workspace tab); the popover content + testids are unchanged.
        """
        locator = self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_POPOVER)
        return PlaywrightWorkspacePeekElement(locator=locator, page=self._page)

    def get_section(self, sub_section: str = "center") -> PlaywrightWorkspaceSection:
        """Get a section POM for a sub-section id.

        ``sub_section`` is a flat sub-section id ("left" | "center" | "right" |
        "bottom", or one suffixed with ":secondary"). Defaults to the center
        section, which hosts the active agent's chat.
        """
        return PlaywrightWorkspaceSection(page=self._page, sub_section=sub_section)

    def get_workspace_tabs(self) -> Locator:
        """Back-compat shim: the sidebar workspace rows (successor to workspace tabs).

        The old top-bar workspace tabs are gone; the sidebar's workspace rows are
        their 1:1 successor (click to navigate, hover to peek, middle-click to
        close), so this returns ``get_workspace_sidebar().get_workspace_rows()``.
        Retained for the regression / real_pi suites that grab "the workspace" by
        position; new tests should call ``get_workspace_sidebar()`` directly.
        """
        return self.get_workspace_sidebar().get_workspace_rows()

    # -- Settings (reachable from the sidebar; the page marker survives) --

    def get_settings_page_locator(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_PAGE)

    # -- Delete-confirmation + inline rename (shared across rows and panel tabs) --

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def confirm_delete(self) -> None:
        """Click the confirm button in the delete-confirmation dialog."""
        confirm_button = self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    # -- Keyboard-shortcuts dialog (cross-cutting survivor) --

    def get_keyboard_shortcuts_dialog(self) -> PlaywrightKeyboardShortcutsDialogElement:
        locator = self.get_by_test_id(ElementIDs.KEYBOARD_SHORTCUTS_DIALOG)
        return PlaywrightKeyboardShortcutsDialogElement(locator=locator, page=self._page)

    # -- Report-a-bug popover (cross-cutting survivor; re-homed to the sidebar) --

    def get_report_problem_popover(self) -> Locator:
        return self.get_by_test_id(ElementIDs.REPORT_PROBLEM_POPOVER)

    # -- Command palette (cross-cutting survivor; open path moves to the sidebar) --

    def get_command_palette(self) -> PlaywrightCommandPaletteElement:
        """Get the command palette locator (visible only when open)."""
        palette = self.get_by_test_id(ElementIDs.COMMAND_PALETTE)
        return PlaywrightCommandPaletteElement(locator=palette, page=self._page)

    def ensure_workspace_exists(self) -> None:
        """Leave the empty first-run state so global shortcuts are live.

        FIRST-03 deliberately disables the command palette AND every global
        keyboard shortcut while no workspace exists: ``areGlobalShortcutsDisabled``
        (derived from an empty workspace list) makes ``useCommandPalette().toggle``
        and ``usePageLayoutKeyboardShortcuts`` no-op, so the sidebar Cmd+K link,
        Cmd+K and Cmd+/ all do nothing. The shared instance's per-test cleanup
        deletes every workspace and lands on the empty first-run page, so a test
        that opens the palette or fires a shortcut must first create a workspace.

        Idempotent: a no-op once any workspace exists (e.g. a test that already
        ran ``start_task_and_wait_for_ready``), so it never disturbs callers that
        are past first-run.
        """
        # Function-local import: project_layout is imported by task_page /
        # settings_page, which playwright_utils imports, so a module-level
        # import here would close that cycle.
        from sculptor.testing.playwright_utils import create_zero_agent_workspace

        if self.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE).is_visible():
            create_zero_agent_workspace(self._page)
            # Global shortcuts + the Cmd+K palette stay disabled until the workspace
            # LIST is non-empty (FIRST-03, driven by workspacesArrayAtom). The create
            # above navigates onto the new workspace, but that list atom can lag the
            # WebSocket sync, so a palette open / shortcut fired immediately can no-op.
            # Wait for the sidebar row (same workspace list) so callers don't race it.
            expect(self.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW).first).to_be_visible()

    def open_command_palette(self) -> PlaywrightCommandPaletteElement:
        """Open the command palette by clicking the sidebar Cmd+K link.

        The open path moved from the old top-bar search button to the sidebar
        ``SIDEBAR_CMDK_LINK`` (SIDE-02); the method signature is unchanged so
        existing callers keep working. A workspace is ensured first because the
        open affordance is disabled in the empty first-run state (FIRST-03).
        """
        self.ensure_workspace_exists()
        cmdk_link = self.get_workspace_sidebar().get_cmdk_link()
        expect(cmdk_link).to_be_visible()
        cmdk_link.click()
        palette = self.get_command_palette()
        expect(palette).to_be_visible()
        return palette

    def open_command_palette_with_keyboard(self) -> PlaywrightCommandPaletteElement:
        """Open the command palette using its default keyboard shortcut.

        A workspace is ensured first because Cmd+K is suppressed in the empty
        first-run state (FIRST-03).
        """
        self.ensure_workspace_exists()
        mod_key = get_playwright_modifier_key()
        self.press_keyboard_shortcut(f"{mod_key}+k")
        palette = self.get_command_palette()
        expect(palette).to_be_visible()
        return palette

    # -- Keyboard helpers (cross-cutting survivor) --

    def press_keyboard_shortcut(self, shortcut: str) -> None:
        self._page.keyboard.press(shortcut)
        # macOS Chromium occasionally fails to emit the modifier keyup
        # after a chord like "Meta+K", leaving the modifier "held" so the
        # next plain keypress (e.g. Escape) arrives as Cmd+Escape and the
        # OS layer can swallow it before the browser sees it. Explicitly
        # release every non-trailing key in the shortcut.
        for modifier in shortcut.split("+")[:-1]:
            self._page.keyboard.up(modifier)

    def toggle_theme(self) -> None:
        """Toggle between dark and light theme via Cmd/Ctrl+Shift+D."""
        mod_key = get_playwright_modifier_key()
        self.press_keyboard_shortcut(f"{mod_key}+Shift+d")

    # -- Warning banner + dialogs (cross-cutting survivors) --

    def get_warning_banner(self) -> PlaywrightWarningBannerElement:
        """Get the warning banner element. Only visible when a warning is active."""
        banner_locator = self.get_by_test_id(ElementIDs.WARNING_STATUS_BANNER)
        return PlaywrightWarningBannerElement(locator=banner_locator, page=self._page)

    def get_git_init_dialog(self) -> PlaywrightGitInitDialogElement:
        dialog_locator = self.get_by_test_id(ElementIDs.PROJECT_GIT_INIT_DIALOG)
        return PlaywrightGitInitDialogElement(locator=dialog_locator, page=self._page)

    def get_add_repo_dialog(self) -> PlaywrightAddRepoDialogElement:
        dialog_locator = self.get_by_test_id(ElementIDs.ADD_REPO_DIALOG)
        return PlaywrightAddRepoDialogElement(locator=dialog_locator, page=self._page)

    def get_project_path_dialog(self) -> PlaywrightProjectPathDialogElement:
        """Get the project path dialog element."""
        dialog_locator = self.get_by_test_id(ElementIDs.PROJECT_PATH_DIALOG)
        return PlaywrightProjectPathDialogElement(locator=dialog_locator, page=self._page)

    # -- Skills panel (survives as a registered panel; content getter kept) --

    def get_skills_panel(self) -> PlaywrightSkillsPanelElement:
        """Get the SkillsPanel element. Only visible when its panel is active."""
        return PlaywrightSkillsPanelElement(self.get_by_test_id(ElementIDs.SKILLS_PANEL), page=self._page)

    def open_skills_panel(self) -> PlaywrightSkillsPanelElement:
        """Reveal the Skills panel (a registered panel) and return it.

        Skills is opened through the section add-panel dropdown like the other
        registered panels.
        """
        open_panel(self._page, "skills", "right")
        panel = self.get_skills_panel()
        expect(panel).to_be_visible()
        return panel
