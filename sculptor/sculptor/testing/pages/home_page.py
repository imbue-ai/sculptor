from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage


class PlaywrightHomePage(PlaywrightIntegrationTestPage):
    """Page Object Model for the home page workspace list."""

    def get_workspace_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_ROW)

    def get_empty_state(self) -> Locator:
        # A brand-new user with zero workspaces lands on the EmptyFirstRunPage
        # (the inline create form), not the home list's own empty state — so the
        # "new user" empty state is keyed by EMPTY_FIRST_RUN_PAGE.
        return self._page.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE)

    def get_search_input(self) -> Locator:
        return self._page.get_by_placeholder("Search workspaces...")

    def get_workspace_row_branch(self, workspace_row: Locator) -> Locator:
        return workspace_row.get_by_test_id(ElementIDs.WORKSPACE_ROW_BRANCH)

    def get_pr_buttons_open(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_OPEN)
