from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class OpenNewRepoDialogElement(PlaywrightIntegrationTestElement):
    """Element representing the 'Open New Repo' dialog."""

    def get_repo_path_input(self):
        """Get the repository path input field."""
        return self.get_by_test_id(ElementIDs.OPEN_NEW_REPO_INPUT)

    def get_confirm_button(self):
        """Get the 'Open' button."""
        return self.get_by_test_id(ElementIDs.CONFIRM_OPEN_NEW_REPO_BUTTON)

    def get_cancel_button(self):
        """Get the 'Cancel' button."""
        return self.get_by_test_id(ElementIDs.CANCEL_OPEN_NEW_REPO_BUTTON)

    def open_project(self, path: str):
        """Fill in the path and click the 'Open' button."""
        self.get_repo_path_input().fill(path)
        self.get_confirm_button().click()
