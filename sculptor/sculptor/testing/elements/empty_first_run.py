from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.pages.task_page import PlaywrightTaskPage


class PlaywrightEmptyFirstRun(PlaywrightIntegrationTestElement):
    """Page Object Model for the empty first-run page.

    With zero workspaces the app gate (``EmptyFirstRunGate``) renders
    ``EmptyFirstRunPage`` in place of every route: the sidebar (open) on the
    left and, in the content area, the ``NewWorkspaceForm`` inline in a
    card with the prompt prefilled to ``/sculptor:help``. Navigation
    is otherwise pared back — Cmd+K and the global shortcuts are off,
    so only this form and Settings are reachable.

    The inline form shares the new-workspace form's field ids, so the form
    getters here mirror ``PlaywrightNewWorkspaceDialog``'s; the sidebar
    empty-state affordances are unique to this page.
    """

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE), page=page)

    # -- Page + inline form --

    def get_page(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE)

    def get_form(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_FORM)

    def get_workspace_name_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)

    def get_prompt_textarea(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_PROMPT_TEXTAREA)

    def get_create_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)

    # -- Sidebar empty-state affordances --

    def get_add_repo_button(self) -> Locator:
        """The "Add a repo" button shown when no repos are registered yet."""
        return self._page.get_by_test_id(ElementIDs.SIDEBAR_ADD_REPO_BUTTON)

    def get_no_workspaces_hint(self) -> Locator:
        """The "No workspaces yet" hint shown under each repo with no workspaces."""
        return self._page.get_by_test_id(ElementIDs.SIDEBAR_NO_WORKSPACES_HINT)

    # -- Suppressed global surfaces --

    def get_command_palette(self) -> Locator:
        """The Cmd+K command palette, which stays closed while the empty state is up."""
        return self._page.get_by_test_id(ElementIDs.COMMAND_PALETTE)

    def get_new_workspace_dialog(self) -> Locator:
        """The standalone new-workspace dialog, suppressed because the form is inline."""
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)

    # -- Create --

    def create_and_wait_for_chat_panel(self, timeout: int = 60_000) -> PlaywrightTaskPage:
        """Create the first workspace and wait for the full workspace page.

        The create navigates to the new agent, flipping the gate off so the
        normal workspace shell takes over and the chat panel renders.
        """
        # The form's source branch comes from repo info, which loads on a separate
        # request from the branch-name preview, and the create button does NOT gate
        # on it while repo info loads. The branch selector mounts only once repo
        # info has loaded, so it is the "source branch resolved" signal — waiting
        # on it makes a repo-info failure surface here, at the unmet precondition,
        # instead of as a downstream timeout. Default timeout on purpose: repo
        # info is retried every 3s up to 10 times after mount, so the selector
        # appears within ~30s or never.
        expect(self._page.get_by_test_id(ElementIDs.BRANCH_SELECTOR)).to_be_visible()
        create_button = self.get_create_button()
        expect(create_button).to_be_enabled()
        create_button.click()
        chat_panel = self._page.get_by_test_id(ElementIDs.CHAT_PANEL)
        expect(chat_panel).to_be_visible(timeout=timeout)
        return PlaywrightTaskPage(page=self._page)
