"""Integration tests for the new-workspace modal (WSC-01..05/07, FIRST-04).

The new-workspace dialog is the sanctioned create surface (Task 5.1..5.3). It is
opened from the Task 5.2 entry points — the Cmd/Meta+T shortcut, the Cmd+K
"New workspace" command, and a repo group's "+" in the sidebar — while the plain
sidebar new-workspace button DIRECT-CREATES (reusing the MRU settings + a fresh
auto branch) and only opens the dialog as a fallback when there is no MRU yet.

These tests cover the dialog's open paths, the WSC-05 form (title + prompt +
context pill + keep-open + create), Cmd+Enter create, the keep-open
reset-but-retain behaviour (Decision B8), prompt-less create, and the
agent-type picker. They run against the non-empty state (a pre-existing
workspace), so the modal — not the empty first-run page — is what opens; the
empty-page first-create path is covered in test_empty_first_run.py.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.elements.user_config import disable_pi_agent
from sculptor.testing.elements.user_config import enable_pi_agent
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _seed_one_workspace(page: object) -> None:
    """Create one workspace so the app is past the empty first-run state.

    The dialog's entry points (Cmd/Meta+T, Cmd+K, the repo "+") are only live
    once a workspace exists — in the empty state the global shortcuts and command
    palette are disabled (FIRST-03). This also persists the MRU settings that the
    sidebar button's direct-create reuses.

    Uses the helper's auto-unique workspace name (no fixed name): the shared instance
    deletes workspaces between tests but their git branches linger, so a fixed seed
    name would auto-generate a colliding branch on the next test.
    """
    start_task_and_wait_for_ready(page, prompt="Say hello")


@user_story("to open the new-workspace dialog with the Cmd/Meta+T shortcut")
def test_modal_opens_via_shortcut(sculptor_instance_: SculptorInstance) -> None:
    """The ``new_workspace`` keybinding (Cmd/Meta+T) opens the dialog (WSC-02)."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    expect(dialog.get_dialog()).to_be_visible()
    expect(dialog.get_form()).to_be_visible()


@user_story("to open the new-workspace dialog from the Cmd+K command palette")
def test_modal_opens_via_command_palette(sculptor_instance_: SculptorInstance) -> None:
    """Cmd+K → "New workspace" (``nav.new_workspace``) opens the dialog (WSC-03)."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_command_palette()

    expect(dialog.get_dialog()).to_be_visible()
    expect(dialog.get_form()).to_be_visible()


@user_story("to open the new-workspace dialog from a repo group's + in the sidebar")
def test_modal_opens_via_repo_plus(sculptor_instance_: SculptorInstance) -> None:
    """A repo group's "+" opens the dialog preselecting that repo (WSC-04)."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    sidebar = get_workspace_sidebar(page)
    repo_group = sidebar.get_repo_groups().first
    expect(repo_group).to_be_visible()
    project_id = repo_group.get_attribute("data-project-id")
    assert project_id is not None, "repo group is missing its data-project-id"

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_repo_plus(project_id)

    expect(dialog.get_dialog()).to_be_visible()
    # The preselected repo seeds the form's source-branch selector, so the branch
    # preview is populated and the form is ready to create.
    expect(dialog.get_branch_name_input()).to_be_visible()


@user_story("to direct-create a workspace from the sidebar button once I have created one before")
def test_sidebar_button_direct_creates_when_mru_exists(sculptor_instance_: SculptorInstance) -> None:
    """The sidebar new-workspace button direct-creates (no dialog) when an MRU exists (WSC-01).

    After a first create, the last-creation settings are remembered, so clicking
    the plain sidebar button reuses them with a fresh auto branch and navigates
    straight to the new agent — the dialog never opens.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    sidebar = get_workspace_sidebar(page)
    expect(sidebar.get_workspace_rows()).to_have_count(1)

    sidebar.get_new_workspace_button().click()

    # Direct-create: a second workspace row appears and the dialog stays closed.
    dialog = PlaywrightNewWorkspaceDialog(page)
    expect(sidebar.get_workspace_rows()).to_have_count(2)
    expect(dialog.get_dialog()).to_have_count(0)


@user_story("to see the new-workspace form's core fields and create control")
def test_form_renders_core_fields(sculptor_instance_: SculptorInstance) -> None:
    """The form renders the title, prompt, branch context pill, keep-open, and create (WSC-05)."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    expect(dialog.get_workspace_name_input()).to_be_visible()
    expect(dialog.get_prompt_textarea()).to_be_visible()
    expect(dialog.get_context_pills()).to_be_visible()
    expect(dialog.get_keep_open_switch()).to_be_visible()
    expect(dialog.get_create_button()).to_be_visible()


@user_story("to create a workspace from the dialog with Cmd+Enter")
def test_cmd_enter_creates_workspace(sculptor_instance_: SculptorInstance) -> None:
    """Cmd+Enter from inside the dialog creates the workspace (WSC-07)."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    dialog.create(workspace_name="Cmd Enter WS", via_keyboard=True)

    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).to_be_visible(timeout=60_000)
    expect(dialog.get_dialog()).to_have_count(0)


@user_story("to create a workspace without typing a prompt")
def test_create_without_prompt(sculptor_instance_: SculptorInstance) -> None:
    """Create with an empty prompt works — the prompt is optional."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    expect(dialog.get_prompt_textarea()).to_have_value("")
    dialog.create_and_wait_for_chat_panel(workspace_name="Promptless WS")

    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible()


@user_story("to keep the dialog open after create, with the repo retained but the title/prompt reset")
def test_keep_open_resets_but_retains(sculptor_instance_: SculptorInstance) -> None:
    """Keep-open resets title/prompt/plan-mode but retains the repo + agent type (Decision B8).

    With keep-open on, Create leaves the dialog open and clears the per-workspace
    fields (title, prompt, branch) while the repo selector keeps its value, ready
    for a rapid second create. Plan mode is per-task, so it also resets to off
    rather than carrying into the next workspace.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    repo_before = dialog.get_project_selector().text_content()
    dialog.get_prompt_textarea().fill("first task")
    # The per-prompt agent settings (incl. plan mode) surface once a prompt is
    # typed. Turn plan mode on for this create so the reset is observable.
    plan_toggle = dialog.get_form().get_by_test_id(ElementIDs.PLAN_MODE_TOGGLE)
    plan_toggle.click()
    expect(plan_toggle).to_have_attribute("data-active", "true")
    # create() normalizes the (persisted) keep-open switch, so request it on here
    # rather than toggling it manually.
    dialog.create(workspace_name="Keep Open WS", keep_open=True)

    # The dialog stays open and the per-workspace fields reset.
    expect(dialog.get_dialog()).to_be_visible()
    expect(dialog.get_workspace_name_input()).to_have_value("")
    expect(dialog.get_prompt_textarea()).to_have_value("")
    # The repo selection is retained.
    expect(dialog.get_project_selector()).to_have_text(repo_before or "")
    # Plan mode does NOT carry over: type a second prompt to reveal the agent
    # settings again and confirm the toggle is back off.
    dialog.get_prompt_textarea().fill("second task")
    expect(plan_toggle).to_have_attribute("data-active", "false")


@user_story("to pick the first agent's type with Claude as the default")
def test_agent_type_picker_defaults_to_claude(sculptor_instance_: SculptorInstance) -> None:
    """The agent-type select defaults to Claude and lists the available types.

    The form's first-agent picker reuses the old page's options: Claude (default)
    and Terminal are always offered; pi is gated behind the experimental
    pi-agent flag. (Decision B2's "no bare Terminal" applies to the panel-tab
    add-dropdown, not to this first-agent select — verified against the rendered
    form, which DOES offer Terminal here.)
    """
    page = sculptor_instance_.page
    # The pi flag is sticky on the shared instance — reset it defensively so the
    # default-off assertion holds.
    disable_pi_agent(page)
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    # Default trigger label is Claude.
    expect(dialog.get_agent_type_select()).to_contain_text("Claude")

    dialog.get_agent_type_select().click()
    expect(dialog.get_agent_type_option_claude()).to_be_visible()
    expect(dialog.get_agent_type_option_terminal()).to_be_visible()
    # pi is hidden while the flag is off.
    expect(dialog.get_agent_type_option_pi()).to_have_count(0)


@user_story("to see the pi agent type in the dialog only when pi-agent is enabled")
def test_agent_type_picker_gates_pi(sculptor_instance_: SculptorInstance) -> None:
    """The pi option appears in the agent-type select only when pi-agent is enabled."""
    page = sculptor_instance_.page
    disable_pi_agent(page)
    _seed_one_workspace(page)

    try:
        enable_pi_agent(page)
        dialog = PlaywrightNewWorkspaceDialog(page)
        dialog.open_via_shortcut()
        dialog.get_agent_type_select().click()
        expect(dialog.get_agent_type_option_pi()).to_be_visible()
        page.keyboard.press("Escape")
    finally:
        disable_pi_agent(page)
