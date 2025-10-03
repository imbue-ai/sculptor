from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.project_git_init_dialog import PlaywrightGitInitDialogElement
from sculptor.testing.elements.project_initial_commit_dialog import PlaywrightInitialCommitDialogElement
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage


class PlaywrightSelectProjectPage(PlaywrightIntegrationTestPage):
    def get_container(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SELECT_PROJECT_PAGE)

    def get_path_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROJECT_PATH_INPUT)

    def get_select_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROJECT_SELECT_BUTTON)

    def get_error_element(self) -> Locator:
        """Get the error message element if displayed."""
        return self.get_by_test_id(ElementIDs.PROJECT_SELECTOR_ERROR)

    def get_git_init_dialog(self) -> PlaywrightGitInitDialogElement:
        dialog = self.get_by_test_id(ElementIDs.PROJECT_GIT_INIT_DIALOG)
        return PlaywrightGitInitDialogElement(locator=dialog, page=self._page)

    def get_initial_commit_dialog(self) -> PlaywrightInitialCommitDialogElement:
        dialog = self.get_by_test_id(ElementIDs.PROJECT_INITIAL_COMMIT_DIALOG)
        return PlaywrightInitialCommitDialogElement(locator=dialog, page=self._page)

    def enter_project_path(self, path: str) -> None:
        """Enter a project path in the input field."""
        path_input = self.get_path_input()
        path_input.clear()
        path_input.fill(path)

    def submit(self) -> None:
        """Click the select button to submit the form."""
        self.get_select_button().click()

    def confirm_git_init(self) -> None:
        """Confirm git initialization in the dialog."""
        git_dialog = self.get_git_init_dialog()
        git_dialog.confirm()
        expect(git_dialog).not_to_be_visible()

    def confirm_initial_commit(self) -> None:
        """Confirm making the initial commit in the dialog."""
        commit_dialog = self.get_initial_commit_dialog()
        commit_dialog.confirm()
        expect(commit_dialog).not_to_be_visible()

    def cancel_git_init(self) -> None:
        """Cancel git initialization in the dialog."""
        git_dialog = self.get_git_init_dialog()
        git_dialog.cancel()

    def complete_project_selection(self, path: str) -> None:
        """High-level helper to complete project selection flow."""
        self.enter_project_path(path)
        self.submit()

    def wait_for_select_project_page_to_be_visible(self) -> None:
        """Wait for the project selector to be visible on the page."""
        expect(self.get_container()).to_be_visible()

    def wait_for_git_init_dialog(self) -> None:
        """Wait for the git initialization dialog to appear."""
        expect(self.get_git_init_dialog()).to_be_visible()

    def wait_for_initial_commit_dialog(self) -> None:
        expect(self.get_initial_commit_dialog()).to_be_visible()

    def wait_for_error_message(self, expected_text: str = None) -> None:
        """Wait for an error message to appear, optionally checking specific text."""
        error = self.get_error_element()
        expect(error).to_be_visible()
        if expected_text:
            expect(error).to_contain_text(expected_text)
