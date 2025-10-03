from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightMergePanel(PlaywrightIntegrationTestElement):
    def get_target_branch_selector(self) -> Locator:
        element = self.get_by_test_id(ElementIDs.MERGE_PANEL_BRANCH_SELECTOR)
        expect(element).to_be_visible()
        return element

    def get_target_branch_options(self) -> Locator:
        container = self._page.get_by_test_id(ElementIDs.MERGE_PANEL_BRANCH_OPTIONS)
        expect(container).to_have_count(1)
        expect(container.first).to_be_visible()
        return container.first.get_by_role("option")

    def get_push_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MERGE_PANEL_PUSH_BUTTON)

    def get_pull_or_fetch_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MERGE_PANEL_PULL_OR_FETCH_BUTTON)

    def pull_or_fetch(self, *, expect_text: str | None = None):
        button = self.get_pull_or_fetch_button()
        if expect_text:
            expect(button).to_contain_text(expect_text)
        button.click()

    def get_footer_with_notices(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MERGE_PANEL_FOOTER_NOTICES)

    def get_all_footer_notices(self) -> Locator:
        return self.get_footer_with_notices().get_by_role("listitem")

    def select_target_branch(self, branch_name: str = None, branch_badge: str = None) -> None:
        """Select a target branch from the dropdown by branch name or badge.

        Args:
            branch_name: The exact branch name to select (e.g., "feature-123")
            branch_badge: The badge text to select by (e.g., "current", "base", "agent's mirror")

        Raises:
            ValueError: If both or neither parameter is provided

        Note: When selecting by branch_name, this searches for the exact branch name
        in the Text element, avoiding accidental matches with badge text.
        When selecting by branch_badge, it finds the option containing that specific badge.
        """
        # Validate that exactly one parameter is provided
        if (branch_name is None) == (branch_badge is None):
            raise ValueError("Must provide exactly one of: branch_name or branch_badge")

        # Open the branch selector dropdown
        branch_selector = self.get_target_branch_selector()
        branch_selector.click()

        # Wait for options to be visible
        options = self.get_target_branch_options()

        if branch_name:
            # Select by branch name - filter options containing this branch name
            branch_option = options.filter(has_text=branch_name).first
            expect(branch_option).to_be_visible()
            branch_option.click()
        else:
            # Select by badge - find the option that contains this badge text
            # Playwright automatically applies the filter relative to the options
            branch_option = options.filter(has=self._page.locator(f"text='{branch_badge}'")).first
            expect(branch_option).to_be_visible()
            branch_option.click()
