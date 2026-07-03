from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWorkspaceSidebarElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the workspace navigation sidebar.

    The sidebar is the global chrome rail that replaces the old top bar + tab
    strip: top links (Home / Cmd+K / New workspace), repos as collapsible groups
    with their workspaces, then Settings / report-a-bug / version at the bottom.

    Workspace rows are the successor to the home page's ``WORKSPACE_ROW`` surface,
    so the row helpers below mirror ``PlaywrightHomePage.get_workspace_rows()``
    rather than inventing a new row model.
    """

    # -- Top links --

    def get_home_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_HOME_LINK)

    def get_cmdk_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_CMDK_LINK)

    def get_new_workspace_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_NEW_WORKSPACE_BUTTON)

    # -- Repo groups --

    def get_repo_groups(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_REPO_GROUP)

    def get_repo_add_workspace(self, project_id: str) -> Locator:
        # The add-workspace icon is stamped with ``data-project-id``; this raw
        # CSS-attribute scope stays inside the POM so the integration-test
        # css-locator ratchet is honoured at the call sites.
        return self._page.locator(
            f'[data-testid="{ElementIDs.SIDEBAR_REPO_ADD_WORKSPACE}"][data-project-id="{project_id}"]'
        )

    # -- Workspace rows (mirrors PlaywrightHomePage.get_workspace_rows) --

    def get_workspace_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)

    def get_workspace_row_by_name(self, name: str) -> Locator:
        return self.get_workspace_rows().filter(has_text=name)

    def get_row_delete_icon(self, workspace_row: Locator) -> Locator:
        """Get the hover-revealed delete icon scoped to a workspace row.

        The delete icon sits in the row's sibling actions cluster (revealed on
        hover), so it is scoped to the row's parent rather than the row button
        itself.
        """
        return workspace_row.locator("..").get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW_DELETE)

    def get_row_menu_icon(self, workspace_row: Locator) -> Locator:
        """Get the hover-revealed "..." actions menu icon scoped to a workspace row."""
        return workspace_row.locator("..").get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW_MENU)

    def open_row_context_menu(self, workspace_row: Locator) -> None:
        """Right-click a workspace row to open its context menu."""
        workspace_row.click(button="right")

    def open_row_dropdown_menu(self, workspace_row: Locator) -> None:
        """Hover a row and click its "..." actions dropdown trigger."""
        workspace_row.hover()
        menu_icon = self.get_row_menu_icon(workspace_row)
        expect(menu_icon).to_be_visible()
        menu_icon.click()

    # -- Workspace-row context menu items + inline rename --
    #
    # The sidebar workspace row shares the workspace-action context menu (the
    # ``TAB_CONTEXT_MENU_*`` ids), reached by right-clicking the row or via the
    # row's "..." dropdown. Rename commits through the shared InlineRenameInput;
    # delete opens the shared DeleteConfirmationDialog, and confirming runs the
    # optimistic removal (the row vanishes before the backend confirms).

    def get_context_menu_rename(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)

    def get_context_menu_delete(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)

    def get_copy_workspace_name_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_WORKSPACE_NAME)

    def get_copy_branch_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_BRANCH)

    def get_copy_workspace_id_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_WORKSPACE_ID)

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)

    def get_delete_confirmation_cancel_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CANCEL)

    def confirm_delete(self) -> None:
        """Click the confirm button in the workspace delete-confirmation dialog."""
        confirm_button = self.get_delete_confirmation_confirm_button()
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    def cancel_delete(self) -> None:
        """Click the cancel button in the workspace delete-confirmation dialog."""
        cancel_button = self.get_delete_confirmation_cancel_button()
        expect(cancel_button).to_be_visible()
        cancel_button.click()

    def open_diagnostics_submenu(self, workspace_row: Locator) -> None:
        """Right-click a row and hover Diagnostics to open the copy-id submenu."""
        self.open_row_context_menu(workspace_row)
        trigger = self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DIAGNOSTICS)
        expect(trigger).to_be_visible()
        trigger.hover()

    def rename_workspace_via_context_menu(self, workspace_row: Locator, new_name: str) -> None:
        """Right-click a row, click Rename, then fill and commit the inline input."""
        self.open_row_context_menu(workspace_row)
        rename_item = self.get_context_menu_rename()
        expect(rename_item).to_be_visible()
        rename_item.click()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()

    def delete_workspace_via_context_menu(self, workspace_row: Locator) -> None:
        """Right-click a row, click Delete, and confirm in the delete dialog.

        Deleting a workspace is destructive, so it is confirmed first; the delete
        itself is then optimistic (the row vanishes before the backend confirms).
        """
        self.open_row_context_menu(workspace_row)
        delete_item = self.get_context_menu_delete()
        expect(delete_item).to_be_visible()
        delete_item.click()
        self.confirm_delete()

    def delete_workspace_via_row_icon(self, workspace_row: Locator) -> None:
        """Hover a row, click its trash icon, and confirm in the delete dialog."""
        workspace_row.hover()
        delete_icon = self.get_row_delete_icon(workspace_row)
        expect(delete_icon).to_be_visible()
        delete_icon.click()
        self.confirm_delete()

    # -- Bottom links + chrome --

    def get_settings_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_SETTINGS_LINK)

    def get_version(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_VERSION)

    def get_collapse_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_COLLAPSE_TOGGLE)

    def get_resize_handle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_RESIZE_HANDLE)

    def get_expand_icon(self) -> Locator:
        """Get the collapsed-sidebar expand toggle.

        Rendered only when the sidebar is collapsed, in place of the sidebar
        rail, so it is located page-wide rather than scoped to the sidebar root.
        """
        return self._page.get_by_test_id(ElementIDs.SIDEBAR_EXPAND_ICON)

    def collapse(self) -> None:
        """Collapse the sidebar to its expand-icon-only rail."""
        toggle = self.get_collapse_toggle()
        expect(toggle).to_be_visible()
        toggle.click()

    def expand(self) -> None:
        """Expand a collapsed sidebar back to the full rail."""
        expand_icon = self.get_expand_icon()
        expect(expand_icon).to_be_visible()
        expand_icon.click()


def get_workspace_sidebar(page: Page) -> PlaywrightWorkspaceSidebarElement:
    """Return the sidebar POM rooted at the ``WORKSPACE_SIDEBAR`` element.

    The sidebar renders on the workspace route's shell layout. When collapsed,
    the rail is replaced by the expand icon, so the root locator is hidden — use
    ``get_expand_icon()`` / ``expand()`` in that state.
    """
    sidebar = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    return PlaywrightWorkspaceSidebarElement(locator=sidebar, page=page)
