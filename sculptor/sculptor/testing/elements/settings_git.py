from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGitSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Git section in Settings."""

    def get_creation_prompt_textarea(self) -> Locator:
        """Get the textarea for editing the PR creation prompt."""
        return self._locator.locator("textarea")

    def get_poll_interval_input(self) -> Locator:
        """Get the number input for poll interval."""
        return self._locator.get_by_test_id(ElementIDs.SETTINGS_POLL_INTERVAL_INPUT)

    def get_default_target_branch_input(self) -> Locator:
        """Get the text input for default target branch.

        Looks up by data-testid; needed because Settings | Git also has a
        "Default branch-naming pattern" text input (added with worktree mode),
        so a section-wide ``input:not([type="number"])`` query is no longer
        unique.
        """
        return self._locator.get_by_test_id(ElementIDs.SETTINGS_DEFAULT_TARGET_BRANCH_INPUT)

    def set_default_target_branch(self, branch: str) -> None:
        """Clear and fill the default target branch input."""
        input_field = self.get_default_target_branch_input()
        input_field.fill(branch)
        input_field.blur()
