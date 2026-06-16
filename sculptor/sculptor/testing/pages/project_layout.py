from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.elements.closed_workspaces_dropdown import PlaywrightClosedWorkspacesDropdownElement
from sculptor.testing.elements.command_palette import PlaywrightCommandPaletteElement
from sculptor.testing.elements.git_init_dialog import PlaywrightGitInitDialogElement
from sculptor.testing.elements.keyboard_shortcuts_dialog import PlaywrightKeyboardShortcutsDialogElement
from sculptor.testing.elements.project_path_dialog import PlaywrightProjectPathDialogElement
from sculptor.testing.elements.skills_panel import PlaywrightSkillsPanelElement
from sculptor.testing.elements.topbar import PlaywrightTopBarElement
from sculptor.testing.elements.warning_banner import PlaywrightWarningBannerElement
from sculptor.testing.elements.workspace_peek import PlaywrightWorkspacePeekElement
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage
from sculptor.testing.utils import get_playwright_modifier_key


class PlaywrightProjectLayoutPage(PlaywrightIntegrationTestPage):
    """Page object for the PageLayout that contains the top bar and main content."""

    def get_home_tab(self) -> Locator:
        return self.get_by_test_id(ElementIDs.HOME_TAB)

    def close_home_tab(self) -> None:
        home_tab = self.get_home_tab()
        close_button = home_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
        close_button.click()

    def get_settings_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_BUTTON)

    def get_settings_tab(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_TAB)

    def open_settings_tab(self) -> Locator:
        self.get_settings_button().click()
        settings_tab = self.get_settings_tab()
        expect(settings_tab).to_be_visible()
        return settings_tab

    def close_settings_tab(self) -> None:
        settings_tab = self.get_settings_tab()
        close_button = settings_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
        close_button.click()

    def get_tab_context_menu_close(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE)

    def get_tab_context_menu_rename(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)

    def get_tab_context_menu_delete(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)

    def get_tab_context_menu_close_all(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_ALL)

    def get_tab_context_menu_close_others(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_OTHERS)

    def get_add_workspace_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ADD_WORKSPACE_BUTTON)

    def get_workspace_tabs(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_TAB)

    def get_add_workspace_tabs(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ADD_WORKSPACE_TAB)

    def close_workspace_tab(self, workspace_tab_index: int = 0) -> None:
        tab = self.get_workspace_tabs().nth(workspace_tab_index)
        tab.click()
        close_button = tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
        close_button.click()

    def close_workspace_tab_via_context_menu(self, workspace_tab_index: int = 0) -> None:
        tab = self.get_workspace_tabs().nth(workspace_tab_index)
        tab.click(button="right")
        close_item = self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE)
        expect(close_item).to_be_visible()
        close_item.click()

    def delete_workspace_via_context_menu(self, workspace_tab_index: int = 0) -> None:
        """Right-click a workspace tab, select Delete, and confirm deletion."""
        tab = self.get_workspace_tabs().nth(workspace_tab_index)
        tab.click(button="right")
        delete_item = self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)
        expect(delete_item).to_be_visible()
        delete_item.click()
        confirm_button = self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def confirm_delete(self) -> None:
        """Click the confirm button in the delete-confirmation dialog."""
        confirm_button = self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    def open_workspace_tab_context_menu(self, workspace_tab_index: int = 0) -> None:
        """Right-click a workspace tab to open the context menu."""
        tab = self.get_workspace_tabs().nth(workspace_tab_index)
        tab.click(button="right")

    def rename_workspace_tab(self, new_name: str, workspace_tab_index: int = 0) -> None:
        """Rename a workspace tab via context menu."""
        self.open_workspace_tab_context_menu(workspace_tab_index)
        rename_item = self.get_tab_context_menu_rename()
        expect(rename_item).to_be_visible()
        rename_item.click()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()

    def get_closed_workspaces_pill(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CLOSED_WORKSPACES_PILL)

    def get_closed_workspaces_dropdown(self) -> PlaywrightClosedWorkspacesDropdownElement:
        dropdown = self._page.get_by_test_id(ElementIDs.CLOSED_WORKSPACES_DROPDOWN)
        return PlaywrightClosedWorkspacesDropdownElement(locator=dropdown, page=self._page)

    def get_workspace_peek_popover(self) -> PlaywrightWorkspacePeekElement:
        popover = self._page.get_by_test_id(ElementIDs.WORKSPACE_PEEK_POPOVER)
        return PlaywrightWorkspacePeekElement(locator=popover, page=self._page)

    def get_topbar(self) -> PlaywrightTopBarElement:
        """Get the topbar element."""
        topbar = self.get_by_test_id(ElementIDs.TOP_BAR)
        return PlaywrightTopBarElement(locator=topbar, page=self._page)

    def get_top_bar_locator(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TOP_BAR)

    def get_bottom_bar(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BOTTOM_BAR)

    def get_component_gallery_tab(self) -> Locator:
        return self.get_by_test_id(ElementIDs.COMPONENT_GALLERY_TAB)

    def get_settings_page_locator(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_PAGE)

    def get_keyboard_shortcuts_dialog(self) -> PlaywrightKeyboardShortcutsDialogElement:
        locator = self.get_by_test_id(ElementIDs.KEYBOARD_SHORTCUTS_DIALOG)
        return PlaywrightKeyboardShortcutsDialogElement(locator=locator, page=self._page)

    def get_report_problem_popover(self) -> Locator:
        return self.get_by_test_id(ElementIDs.REPORT_PROBLEM_POPOVER)

    def get_command_palette(self) -> PlaywrightCommandPaletteElement:
        """Get the command palette locator (visible only when open)."""
        palette = self.get_by_test_id(ElementIDs.COMMAND_PALETTE)
        return PlaywrightCommandPaletteElement(locator=palette, page=self._page)

    def open_command_palette(self) -> PlaywrightCommandPaletteElement:
        """Open the command palette by clicking the topbar button."""
        self.get_topbar().open_command_palette()
        palette = self.get_command_palette()
        expect(palette).to_be_visible()
        return palette

    def open_command_palette_with_keyboard(self) -> PlaywrightCommandPaletteElement:
        """Open the command palette using its default keyboard shortcut."""
        mod_key = get_playwright_modifier_key()
        self.press_keyboard_shortcut(f"{mod_key}+k")
        palette = self.get_command_palette()
        expect(palette).to_be_visible()
        return palette

    def press_keyboard_shortcut(self, shortcut: str) -> None:
        self._page.keyboard.press(shortcut)
        # macOS Chromium occasionally fails to emit the modifier keyup
        # after a chord like "Meta+K", leaving the modifier "held" so the
        # next plain keypress (e.g. Escape) arrives as Cmd+Escape and the
        # OS layer can swallow it before the browser sees it. Explicitly
        # release every non-trailing key in the shortcut.
        for modifier in shortcut.split("+")[:-1]:
            self._page.keyboard.up(modifier)

    def get_warning_banner(self) -> PlaywrightWarningBannerElement | None:
        """Get the warning banner element if it's visible."""
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

    def get_skills_panel(self) -> PlaywrightSkillsPanelElement:
        """Get the SkillsPanel element. Only visible when its zone is open."""
        return PlaywrightSkillsPanelElement(self.get_by_test_id(ElementIDs.SKILLS_PANEL), page=self._page)

    def toggle_theme(self) -> None:
        """Toggle between dark and light theme via Cmd/Ctrl+Shift+D."""
        mod_key = get_playwright_modifier_key()
        self.press_keyboard_shortcut(f"{mod_key}+Shift+d")

    def open_skills_panel(self) -> PlaywrightSkillsPanelElement:
        """Click the skills sidebar icon and return the visible SkillsPanel.

        The panel lives in the right zone, collapsed by default. Clicking its
        sidebar icon both reveals the zone and switches to the skills panel.
        """
        sidebar_icon = self.get_by_test_id(ElementIDs.PANEL_ICON_SKILLS)
        expect(sidebar_icon).to_be_visible()
        sidebar_icon.click()
        panel = self.get_skills_panel()
        expect(panel).to_be_visible()
        return panel
