from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWorkspaceSidebarElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the workspace navigation sidebar (SIDE-*).

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

    def get_repo_group_by_project_id(self, project_id: str) -> Locator:
        """Locate a repo group's header button by its project id.

        The component stamps ``data-project-id`` on the group header, the
        repo-settings icon, and the add-workspace icon. CSS-attribute scoping
        stays inside the POM to honour the integration-test css-locator ratchet.
        """
        return self._page.locator(f'[data-testid="{ElementIDs.SIDEBAR_REPO_GROUP}"][data-project-id="{project_id}"]')

    def collapse_repo_group(self, project_id: str) -> None:
        """Toggle a repo group's collapsed state by clicking its header."""
        self.get_repo_group_by_project_id(project_id).click()

    def get_repo_add_workspace(self, project_id: str) -> Locator:
        return self._page.locator(
            f'[data-testid="{ElementIDs.SIDEBAR_REPO_ADD_WORKSPACE}"][data-project-id="{project_id}"]'
        )

    def get_repo_settings(self, project_id: str) -> Locator:
        return self._page.locator(
            f'[data-testid="{ElementIDs.SIDEBAR_REPO_SETTINGS}"][data-project-id="{project_id}"]'
        )

    # -- Workspace rows (mirrors PlaywrightHomePage.get_workspace_rows) --

    def get_workspace_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)

    def get_workspace_row_by_name(self, name: str) -> Locator:
        return self.get_workspace_rows().filter(has_text=name)

    def get_workspace_row_by_id(self, workspace_id: str) -> Locator:
        """Locate a workspace row by its workspace id (``data-workspace-id``)."""
        return self._page.locator(
            f'[data-testid="{ElementIDs.SIDEBAR_WORKSPACE_ROW}"][data-workspace-id="{workspace_id}"]'
        )

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

    # -- Bottom links + chrome --

    def get_settings_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_SETTINGS_LINK)

    def get_report_bug(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_REPORT_BUG)

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
