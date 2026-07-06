from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import open_new_workspace_modal
from sculptor.testing.utils import get_playwright_modifier_key


class PlaywrightNewWorkspaceDialog(PlaywrightIntegrationTestElement):
    """Page Object Model for the new-workspace modal.

    The modal hosts the ``NewWorkspaceForm`` inside a ``PaletteDialog``
    (``NEW_WORKSPACE_DIALOG``). It is opened by several entry points — the sidebar's
    "New Workspace" nav button (``SIDEBAR_NEW_WORKSPACE_BUTTON``), the Cmd/Meta+T
    shortcut (``new_workspace`` keybinding), and the Cmd+K ``nav.new_workspace``
    command. The per-repo "+" in the sidebar repo groups instead direct-creates a
    workspace in that repo, only falling back to this dialog when the branch can't be
    resolved or the create fails.

    The form's field ids are shared with the inline empty-first-run form, so the
    getters here are mirrored by ``PlaywrightEmptyFirstRun``. Only one form
    renders at a time, so the field getters resolve page-wide; the create button
    is the modal's ``NEW_WORKSPACE_CREATE_BUTTON``.
    """

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG), page=page)

    # -- Openers (entry points) --

    def open_via_shortcut(self) -> None:
        """Open the modal with the ``new_workspace`` keybinding (Cmd/Meta+T).

        Delegates to the hardened opener: the shortcut is a window keydown handler
        whose single press can be swallowed when focus sits in the chat input (a prior
        ``start_task_and_wait_for_ready`` leaves it focused) or in a Radix overlay, so
        the opener dismisses any intercepting overlay and blurs the active element
        before each press and retries until the modal mounts.
        """
        open_new_workspace_modal(self._page)
        expect(self.get_dialog()).to_be_visible()

    def open_via_command_palette(self) -> None:
        """Open the modal through Cmd+K → the "New workspace" command.

        Drives the command palette POM to run the ``nav.new_workspace`` command,
        whose ``perform`` opens this modal rather than navigating to ``/ws/new``.
        """
        project_layout = PlaywrightProjectLayoutPage(page=self._page)
        palette = project_layout.open_command_palette_with_keyboard()
        palette.select_by_command_id("nav.new_workspace")
        expect(self.get_dialog()).to_be_visible()

    def open_via_sidebar_button(self) -> None:
        """Open the modal via the sidebar's "New Workspace" nav button.

        The per-repo "+" direct-creates (no dialog); this nav button is the
        sidebar's open-the-dialog affordance. The form seeds its repo from the
        most recently used project.
        """
        button = self._page.get_by_test_id(ElementIDs.SIDEBAR_NEW_WORKSPACE_BUTTON)
        expect(button).to_be_visible()
        button.click()
        expect(self.get_dialog()).to_be_visible()

    # -- Dialog shell --

    def get_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)

    def get_form(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_FORM)

    # -- Form fields (shared with the /ws/new page and the inline first-run form) --

    def get_workspace_name_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)

    def get_prompt_textarea(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_PROMPT_TEXTAREA)

    def get_context_pills(self) -> Locator:
        """The branch-name context pill.

        ``NEW_WORKSPACE_CONTEXT_PILL`` is the branch field's pill container; the
        repo / agent-type / mode / source controls are their own selectors below.
        """
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CONTEXT_PILL)

    def get_keep_open_switch(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_KEEP_OPEN_SWITCH)

    def set_keep_open(self, enabled: bool) -> None:
        """Force the keep-open switch to ``enabled``.

        The switch is PERSISTED (it survives reloads and leaks across tests in a
        shared instance), so creators normalize it rather than assume a default —
        otherwise a prior keep-open test would leave the dialog open + non-navigating
        for later creates. Reads the Radix switch's ``aria-checked`` and toggles only
        on a mismatch.
        """
        switch = self.get_keep_open_switch()
        expect(switch).to_be_visible()
        is_on = switch.get_attribute("aria-checked") == "true"
        if is_on != enabled:
            switch.click()
            expect(switch).to_have_attribute("aria-checked", "true" if enabled else "false")

    # -- Repo selector --

    def get_project_selector(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PROJECT_SELECTOR)

    def get_project_options(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PROJECT_SELECT_ITEM)

    def select_project_by_name(self, project_name: str) -> None:
        self.get_project_selector().click()
        project_option = self.get_project_options().filter(has_text=project_name)
        expect(project_option).to_be_visible()
        project_option.click()

    def get_open_new_repo_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.OPEN_NEW_REPO_BUTTON)

    # -- Agent-type selector --

    def get_agent_type_select(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT)

    def get_agent_type_option_claude(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_CLAUDE)

    def get_agent_type_option_pi(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_PI)

    def get_agent_type_option_terminal(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_TERMINAL)

    def select_agent_type(self, agent_type_option_id: str) -> None:
        """Open the agent-type select and choose an option by its test id."""
        self.get_agent_type_select().click()
        option = self._page.get_by_test_id(agent_type_option_id)
        expect(option).to_be_visible()
        option.click()
        expect(option).not_to_be_visible()

    # -- Plan-mode toggle (per-prompt agent setting; surfaces once a prompt is typed) --

    def get_plan_mode_toggle(self) -> Locator:
        # Scoped to the form, unlike the page-wide field getters above: the chat
        # panel's input renders its own PLAN_MODE_TOGGLE, and in keep-open flows a
        # created workspace's chat panel is mounted under the still-open dialog,
        # so a page-wide locator is ambiguous (Playwright strict-mode violation).
        return self.get_form().get_by_test_id(ElementIDs.PLAN_MODE_TOGGLE)

    # -- Mode selector --

    def get_mode_selector(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MODE_SELECTOR)

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

    # -- Source-branch selector --

    def get_branch_selector(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_SELECTOR)

    def select_branch(self, branch_name: str) -> None:
        self.get_branch_selector().click()
        branch_option = (
            self._page.get_by_test_id(ElementIDs.BRANCH_OPTION).filter(has_text=branch_name).filter(has_not_text="*")
        )
        expect(branch_option).to_have_count(1)
        branch_option.click()

    # -- Branch-name pill --

    def get_branch_name_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)

    def get_branch_name_collision_error(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_NAME_COLLISION_ERROR)

    def get_branch_shuffle_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_NAME_SHUFFLE_BUTTON)

    # -- Create --

    def get_create_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)

    def create(self, workspace_name: str | None = None, via_keyboard: bool = False, keep_open: bool = False) -> None:
        """Fill the title (optional) and create, by button click or Cmd+Enter.

        Normalizes the persisted keep-open switch to ``keep_open`` first (default off,
        so the dialog closes and navigates to the new workspace). Waits for the create
        button to enable — in worktree mode submit is gated on the branch-name preview.
        """
        if workspace_name is not None:
            self.get_workspace_name_input().fill(workspace_name)
        self.set_keep_open(keep_open)
        # The form's source branch comes from repo info, which loads on a separate
        # request from the branch-name preview, and the create button does NOT gate
        # on it while repo info loads. The branch selector mounts only once repo
        # info has loaded (in every mode), so it is the "source branch resolved"
        # signal — waiting on it makes a repo-info failure surface here, at the
        # unmet precondition, instead of as a downstream timeout. Default timeout
        # on purpose: repo info is retried every 3s up to 10 times after mount,
        # so the selector appears within ~30s or never.
        expect(self.get_branch_selector()).to_be_visible()
        create_button = self.get_create_button()
        expect(create_button).to_be_enabled()
        if via_keyboard:
            mod_key = get_playwright_modifier_key()
            self._page.keyboard.press(f"{mod_key}+Enter")
            self._page.keyboard.up(mod_key)
        else:
            create_button.click()

    def create_and_wait_for_chat_panel(
        self, workspace_name: str | None = None, via_keyboard: bool = False, timeout: int = 60_000
    ) -> PlaywrightTaskPage:
        """Create a workspace (keep-open forced off) and wait for it to commit.

        Waits for the dialog to CLOSE first (it closes via onCreated only once the
        create has navigated to the new workspace), so this doesn't return early on a
        pre-existing (seed) workspace's chat panel while the create is still in flight.
        """
        self.create(workspace_name=workspace_name, via_keyboard=via_keyboard, keep_open=False)
        expect(self.get_dialog()).to_have_count(0, timeout=timeout)
        chat_panel = self._page.get_by_test_id(ElementIDs.CHAT_PANEL)
        expect(chat_panel).to_be_visible(timeout=timeout)
        return PlaywrightTaskPage(page=self._page)
