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

    Navigation lives in the sidebar (``get_workspace_sidebar()``) and content
    in the section grid (``get_section()``). This page object also exposes the
    cross-cutting surfaces layered over the shell: keyboard shortcuts, the
    command palette, the warning banner, and the git-init / add-repo /
    project-path / keyboard-shortcuts dialogs.
    """

    # -- Sidebar + sections (the new layout spine) --

    def get_workspace_sidebar(self) -> PlaywrightWorkspaceSidebarElement:
        """Get the workspace navigation sidebar POM."""
        return get_workspace_sidebar(self._page)

    def get_workspace_peek_popover(self) -> PlaywrightWorkspacePeekElement:
        """Get the workspace peek popover POM (visible only while hovering a sidebar row).

        The peek follows the hovered workspace **row** in the sidebar.
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

    # -- Settings (reachable from the sidebar) --

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

    # -- Keyboard-shortcuts dialog (cross-cutting) --

    def get_keyboard_shortcuts_dialog(self) -> PlaywrightKeyboardShortcutsDialogElement:
        locator = self.get_by_test_id(ElementIDs.KEYBOARD_SHORTCUTS_DIALOG)
        return PlaywrightKeyboardShortcutsDialogElement(locator=locator, page=self._page)

    # -- Report-a-bug popover (cross-cutting; opened from the sidebar) --

    def get_report_problem_popover(self) -> Locator:
        return self.get_by_test_id(ElementIDs.REPORT_PROBLEM_POPOVER)

    # -- Command palette (cross-cutting; opened from the sidebar) --

    def get_command_palette(self) -> PlaywrightCommandPaletteElement:
        """Get the command palette locator (visible only when open)."""
        palette = self.get_by_test_id(ElementIDs.COMMAND_PALETTE)
        return PlaywrightCommandPaletteElement(locator=palette, page=self._page)

    def ensure_workspace_exists(self) -> None:
        """Create a workspace when the loaded list is empty.

        The shared instance's per-test cleanup deletes every workspace, but most
        palette commands and shortcuts the tests drive act on a workspace
        surface (panels, tabs, agents), so a test that exercises them must first
        create one. Creating here also keeps the auto-opened first-run
        new-workspace dialog (Home pops it while the list is empty) out of the
        way of subsequent clicks.

        Idempotent: a no-op once any workspace exists (e.g. a test that already
        ran ``start_task_and_wait_for_ready``), so it never disturbs callers that
        are past first-run.
        """
        # Function-local import: project_layout is imported by task_page /
        # settings_page, which playwright_utils imports, so a module-level
        # import here would close that cycle.
        from sculptor.testing.playwright_utils import create_zero_agent_workspace
        from sculptor.testing.playwright_utils import wait_for_workspace_list_loaded

        # The momentary is_visible() probe below can't distinguish "list still
        # loading" (the sidebar's empty affordances deliberately don't render
        # then) from "list loaded with workspaces" — settle the load first, or a
        # slow runner skips the create and later steps act on the wrong state.
        wait_for_workspace_list_loaded(self._page)

        # The per-repo "No workspaces yet" hint is the loaded-and-empty signal
        # (the persistent "Add repo" nav button renders regardless, so it can't
        # distinguish anything).
        sidebar_empty = self.get_by_test_id(ElementIDs.SIDEBAR_NO_WORKSPACES_HINT).first
        if sidebar_empty.is_visible():
            create_zero_agent_workspace(self._page)
            # The create above navigates onto the new workspace, but the
            # workspace list atom can lag the WebSocket sync. Wait for the
            # sidebar row (same workspace list) so callers don't race it.
            expect(self.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW).first).to_be_visible()
            # If Home auto-opened the first-run new-workspace dialog before the
            # create, it stays open (it only closes on its own create/dismiss
            # or on leaving Home) and its panel would sit over content the
            # caller interacts with next — close it.
            new_workspace_dialog = self.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)
            if new_workspace_dialog.count() > 0:
                self._page.keyboard.press("Escape")
                expect(new_workspace_dialog).to_have_count(0)

    def open_command_palette(self) -> PlaywrightCommandPaletteElement:
        """Open the command palette by clicking the sidebar Cmd+K link.

        Clicks the sidebar ``SIDEBAR_CMDK_LINK``. A workspace is ensured first
        because the palette commands the tests then run act on one.
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

        A workspace is ensured first because the palette commands the tests
        then run act on one.
        """
        self.ensure_workspace_exists()
        mod_key = get_playwright_modifier_key()
        self.press_keyboard_shortcut(f"{mod_key}+k")
        palette = self.get_command_palette()
        expect(palette).to_be_visible()
        return palette

    # -- Keyboard helpers (cross-cutting) --

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

    # -- Warning banner + dialogs (cross-cutting) --

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

    # -- Skills panel (a registered panel) --

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
