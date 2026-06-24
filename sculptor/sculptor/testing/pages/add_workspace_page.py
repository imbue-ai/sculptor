from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightAddWorkspacePage(PlaywrightProjectLayoutPage):
    """Page object for the new-workspace MODAL (formerly the /ws/new page).

    The legacy ``/ws/new`` page is gone; this now drives the new-workspace modal
    (and the inline empty-first-run form, which shares the same field testids).
    The create button and prompt input are re-pointed at the modal's
    ``NEW_WORKSPACE_CREATE_BUTTON`` / ``NEW_WORKSPACE_PROMPT_TEXTAREA``; the
    remaining getters already use testids shared across both surfaces.
    """

    def get_project_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROJECT_SELECTOR)

    def get_project_options(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROJECT_SELECT_ITEM)

    def select_project_by_name(self, project_name: str) -> None:
        self.get_project_selector().click()
        project_option = self.get_project_options().filter(has_text=project_name)
        expect(project_option).to_be_visible()
        project_option.click()

    def get_open_new_repo_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.OPEN_NEW_REPO_BUTTON)

    def open_add_repo_dialog(self) -> PlaywrightAddRepoDialogElement:
        """Open the 'Add Repository' dialog from the repo selector."""
        self.get_project_selector().click()
        self.get_open_new_repo_button().click()
        dialog = PlaywrightAddRepoDialogElement(
            locator=self.get_by_test_id(ElementIDs.ADD_REPO_DIALOG), page=self._page
        )
        expect(dialog.get_path_input()).to_be_visible()
        return dialog

    def get_task_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.NEW_WORKSPACE_PROMPT_TEXTAREA)

    def get_workspace_name_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)

    def get_submit_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)

    def get_branch_name_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)

    def get_branch_name_collision_error(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_NAME_COLLISION_ERROR)

    def get_branch_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_SELECTOR)

    def select_branch(self, branch_name: str) -> None:
        self.get_branch_selector().click()
        branch_option = (
            self.get_by_test_id(ElementIDs.BRANCH_OPTION).filter(has_text=branch_name).filter(has_not_text="*")
        )
        expect(branch_option).to_have_count(1)
        branch_option.click()

    def get_mode_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MODE_SELECTOR)

    def get_mode_option_worktree(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MODE_OPTION_WORKTREE)

    def get_mode_option_in_place(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MODE_OPTION_IN_PLACE)

    def get_mode_option_clone(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MODE_OPTION_CLONE)

    def select_mode(self, mode_option_id: str) -> None:
        """Click the mode selector and choose a mode option."""
        self.get_mode_selector().click()
        mode_option = self._page.get_by_test_id(mode_option_id)
        expect(mode_option).to_be_visible()
        mode_option.click()
        expect(mode_option).not_to_be_visible()

    def get_chat_panel(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_PANEL)

    def submit_and_wait_for_chat_panel(self, timeout: int = 60_000) -> None:
        """Click the submit button and wait for the chat panel to appear."""
        submit_button = self.get_submit_button()
        expect(submit_button).to_be_enabled()
        submit_button.click()
        expect(self.get_chat_panel()).to_be_visible(timeout=timeout)
