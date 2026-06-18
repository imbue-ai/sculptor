import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightNewWorkspaceModalPage(PlaywrightProjectLayoutPage):
    """Page object for the New Workspace modal.

    The legacy ``/ws/new`` page was replaced by a modal that shares the
    command-palette chrome; this POM wraps the modal's fields (repo, mode,
    source branch, branch name, workspace name, prompt) and the submit button.
    Open the modal first via ``open_new_workspace_modal`` (the topbar
    "+" button).
    """

    def get_new_workspace_modal(self) -> Locator:
        """The modal container — visible only while the modal is open."""
        return self.get_by_test_id(ElementIDs.NEW_WORKSPACE_MODAL)

    def get_inline_new_workspace_form(self) -> Locator:
        """The inline form rendered on an empty Home page (no modal chrome).

        At zero workspaces the create surface is this inline form rather than
        the modal, so count-0 tests assert against this instead of
        ``get_new_workspace_modal``.
        """
        return self.get_by_test_id(ElementIDs.HOME_NEW_WORKSPACE_FORM)

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
        return self.get_by_test_id(ElementIDs.TASK_INPUT)

    def get_workspace_name_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)

    def get_prompt_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.NEW_WORKSPACE_PROMPT_INPUT)

    def get_submit_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.START_TASK_BUTTON)

    def get_branch_name_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)

    def read_branch_name(self) -> str:
        """Return the full branch name currently shown in the branch field."""
        return self.get_branch_name_input().input_value()

    def wait_for_branch_preview(self, expected_value: str | re.Pattern[str] = re.compile(r".+")) -> str:
        """Wait for the auto-filled branch name to populate, then return it.

        Worktree mode gates submit on a non-empty branch name, so tests must
        wait for the debounced preview to land before submitting.
        """
        branch_input = self.get_branch_name_input()
        expect(branch_input).to_be_visible()
        expect(branch_input).to_have_value(expected_value)
        return self.read_branch_name()

    def get_branch_name_reset_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_NAME_RESET_BUTTON)

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
        """Click the mode selector and choose a mode option.

        The mode selector is only rendered when clone or in-place is enabled
        via the user-config flags — worktree is the default and needs no
        selection. Tests must enable the relevant flag before calling this.
        """
        self.get_mode_selector().click()
        mode_option = self._page.get_by_test_id(mode_option_id)
        expect(mode_option).to_be_visible()
        mode_option.click()
        expect(mode_option).not_to_be_visible()

    def select_clone_mode(self) -> None:
        """Select CLONE mode (requires ``enable_clone_workspaces`` first)."""
        self.select_mode(ElementIDs.MODE_OPTION_CLONE)

    def select_in_place_mode(self) -> None:
        """Select IN_PLACE mode (requires ``enable_in_place_workspaces`` first)."""
        self.select_mode(ElementIDs.MODE_OPTION_IN_PLACE)

    def get_chat_panel(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_PANEL)

    def submit_and_wait_for_chat_panel(self, timeout: int = 60_000) -> None:
        """Click the submit button and wait for the chat panel to appear."""
        submit_button = self.get_submit_button()
        expect(submit_button).to_be_enabled()
        submit_button.click()
        expect(self.get_chat_panel()).to_be_visible(timeout=timeout)
