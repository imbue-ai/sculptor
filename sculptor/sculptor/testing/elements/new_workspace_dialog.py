from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.utils import get_playwright_modifier_key


class PlaywrightNewWorkspaceDialog(PlaywrightIntegrationTestElement):
    """Page Object Model for the new-workspace modal.

    The modal hosts the ``NewWorkspaceForm`` inside a ``PaletteDialog``
    (``NEW_WORKSPACE_DIALOG``). It is opened by several entry points — the
    Cmd/Meta+T shortcut (``new_workspace`` keybinding), the Cmd+K
    ``nav.new_workspace`` command, and the sidebar repo group's "+"
    The plain sidebar new-workspace button
    direct-creates and only falls back to opening this when there is no MRU yet.

    The form's field ids are shared with the (still-present) ``/ws/new`` page and
    with the inline empty-first-run form, so the getters here are reused by
    ``PlaywrightEmptyFirstRun``. Only one form renders at a time, so the field
    getters resolve page-wide; the create button is re-pointed to the modal's
    ``NEW_WORKSPACE_CREATE_BUTTON`` (not the legacy ``START_TASK_BUTTON``).
    """

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG), page=page)

    # -- Openers (entry points) --

    def open_via_shortcut(self) -> None:
        """Open the modal with the ``new_workspace`` keybinding (Cmd/Meta+T)."""
        mod_key = get_playwright_modifier_key()
        self._page.keyboard.press(f"{mod_key}+t")
        self._page.keyboard.up(mod_key)
        expect(self.get_dialog()).to_be_visible()

    def open_via_command_palette(self) -> None:
        """Open the modal through Cmd+K → the "New workspace" command.

        Drives the command palette POM to run the ``nav.new_workspace`` command,
        whose ``perform`` opens this modal rather than navigating to ``/ws/new``.
        """
        # Late import to avoid a cycle: project_layout imports command_palette,
        # and the page object below pulls in project_layout.
        from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage

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

    # -- Repo selector (ported from the /ws/new page POM) --

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

    # -- Mode selector (ported from the /ws/new page POM) --

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

    # -- Source-branch selector (ported from the /ws/new page POM) --

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

    def get_branch_reset_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_NAME_RESET_BUTTON)

    # -- Create --

    def get_create_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)

    def get_submit_button(self) -> Locator:
        """Alias of ``get_create_button`` (matches the /ws/new page POM's name)."""
        return self.get_create_button()

    def create(self, workspace_name: str | None = None, via_keyboard: bool = False, keep_open: bool = False) -> None:
        """Fill the title (optional) and create, by button click or Cmd+Enter.

        Normalizes the persisted keep-open switch to ``keep_open`` first (default off,
        so the dialog closes and navigates to the new workspace). Waits for the create
        button to enable — in worktree mode submit is gated on the branch-name preview.
        """
        if workspace_name is not None:
            self.get_workspace_name_input().fill(workspace_name)
        self.set_keep_open(keep_open)
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
