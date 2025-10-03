from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGitPanelPopoverElement(PlaywrightIntegrationTestElement):
    def get_git_pull_button(self) -> Locator:
        """Get the git pull button in the task header."""
        return self.get_by_test_id(ElementIDs.GIT_PULL_BUTTON)

    def get_git_commit_message_input(self) -> Locator:
        """Get the git commit message input in the task header."""
        return self.get_by_test_id(ElementIDs.GIT_COMMIT_MESSAGE_INPUT)

    def get_git_commit_and_push_button(self) -> Locator:
        """Get the git commit and push button in the task header."""
        return self.get_by_test_id(ElementIDs.GIT_COMMIT_AND_PUSH_BUTTON)

    def get_git_fetch_copy_button(self) -> Locator:
        """Get the git fetch copy button in the git panel."""
        return self.get_by_test_id(ElementIDs.GIT_FETCH_COPY_BUTTON)

    def get_git_merge_copy_button(self) -> Locator:
        """Get the git merge copy button in the git panel."""
        return self.get_by_test_id(ElementIDs.GIT_MERGE_COPY_BUTTON)

    def get_git_switch_copy_button(self) -> Locator:
        """Get the git switch copy button in the git panel."""
        return self.get_by_test_id(ElementIDs.GIT_SWITCH_COPY_BUTTON)
