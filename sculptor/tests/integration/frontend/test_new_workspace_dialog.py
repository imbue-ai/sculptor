"""Integration tests for the new-workspace modal.

The new-workspace dialog is the sanctioned create surface. It is
opened from three entry points — the Cmd/Meta+T shortcut, the Cmd+K
"New workspace" command, and a repo group's "+" in the sidebar — while the plain
sidebar new-workspace button DIRECT-CREATES (reusing the MRU settings + a fresh
auto branch) and only opens the dialog as a fallback when there is no MRU yet.

These tests cover the dialog's open paths, the form (title + prompt +
context pill + keep-open + create), Cmd+Enter create, the keep-open
reset-but-retain behaviour, prompt-less create, the agent-type
picker, post-create focus (the chat input holds focus; a terminal first agent
lands in the terminal panel instead), and the ``focus_input`` keybinding. They
run against the non-empty state (a pre-existing workspace), so the modal — not
the empty first-run page — is what opens; the empty-page first-create path is
covered in test_empty_first_run.py.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.elements.terminal import expect_terminal_panel_replaces_chat
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import blur_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _seed_one_workspace(page: Page) -> None:
    """Create one workspace so the app is past the empty first-run state.

    The dialog's entry points (Cmd/Meta+T, Cmd+K, the repo "+") are only live
    once a workspace exists — in the empty state the global shortcuts and command
    palette are disabled. This also persists the MRU settings that the
    sidebar button's direct-create reuses.

    Uses the helper's auto-unique workspace name (no fixed name): the shared instance
    deletes workspaces between tests but their git branches linger, so a fixed seed
    name would auto-generate a colliding branch on the next test.
    """
    start_task_and_wait_for_ready(page, prompt="Say hello")


@user_story("to open the new-workspace dialog with the Cmd/Meta+T shortcut")
def test_modal_opens_via_shortcut(sculptor_instance_: SculptorInstance) -> None:
    """The ``new_workspace`` keybinding (Cmd/Meta+T) opens the dialog."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    expect(dialog.get_dialog()).to_be_visible()
    expect(dialog.get_form()).to_be_visible()


@user_story("to open the new-workspace dialog from the Cmd+K command palette")
def test_modal_opens_via_command_palette(sculptor_instance_: SculptorInstance) -> None:
    """Cmd+K → "New workspace" (``nav.new_workspace``) opens the dialog."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_command_palette()

    expect(dialog.get_dialog()).to_be_visible()
    expect(dialog.get_form()).to_be_visible()


@user_story("to open the new-workspace dialog from the sidebar's New Workspace button")
def test_modal_opens_via_sidebar_button(sculptor_instance_: SculptorInstance) -> None:
    """The sidebar's New Workspace nav button opens the dialog."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_sidebar_button()

    expect(dialog.get_dialog()).to_be_visible()
    # The MRU repo seeds the form's source-branch selector, so the branch
    # preview is populated and the form is ready to create.
    expect(dialog.get_branch_name_input()).to_be_visible()


@user_story("to create a workspace in a repo with one click on its +")
def test_repo_plus_direct_creates(sculptor_instance_: SculptorInstance) -> None:
    """A repo group's "+" direct-creates a workspace in that repo (no dialog).

    After a first create, the last-creation settings are remembered, so the
    repo "+" reuses them with a fresh auto branch and navigates straight to the
    new agent — the dialog never opens.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    sidebar = get_workspace_sidebar(page)
    expect(sidebar.get_workspace_rows()).to_have_count(1)
    repo_group = sidebar.get_repo_groups().first
    expect(repo_group).to_be_visible()
    project_id = repo_group.get_attribute("data-project-id")
    assert project_id is not None, "repo group is missing its data-project-id"

    sidebar.get_repo_add_workspace(project_id).click()

    # Direct-create: a second workspace row appears and the dialog stays closed.
    dialog = PlaywrightNewWorkspaceDialog(page)
    expect(sidebar.get_workspace_rows()).to_have_count(2)
    expect(dialog.get_dialog()).to_have_count(0)


@user_story("to see the new-workspace form's core fields and create control")
def test_form_renders_core_fields(sculptor_instance_: SculptorInstance) -> None:
    """The form renders the title, prompt, branch context pill, keep-open, and create."""
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
    """Cmd+Enter from inside the dialog creates the workspace."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    # create_and_wait_for_chat_panel waits for the dialog to CLOSE (via onCreated,
    # after the create navigates) before checking the chat panel, so it doesn't
    # pass on the seed workspace's still-mounted chat panel under the overlay.
    dialog.create_and_wait_for_chat_panel(workspace_name="Cmd Enter WS", via_keyboard=True)


@user_story("to create a workspace without typing a prompt")
def test_create_without_prompt(sculptor_instance_: SculptorInstance) -> None:
    """Create with an empty prompt works — the prompt is optional."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    expect(dialog.get_prompt_textarea()).to_have_value("")
    # create_and_wait_for_chat_panel asserts the dialog closed and the chat panel
    # is visible, which is the whole point here: create succeeds with no prompt.
    dialog.create_and_wait_for_chat_panel(workspace_name="Promptless WS")


@user_story("to keep the dialog open after create, with the repo retained but the title/prompt reset")
def test_keep_open_resets_but_retains(sculptor_instance_: SculptorInstance) -> None:
    """Keep-open resets title/prompt/plan-mode but retains the repo + agent type.

    With keep-open on, Create leaves the dialog open and clears the per-workspace
    fields (title, prompt, branch) while the repo selector keeps its value, ready
    for a rapid second create. Plan mode is per-task, so it also resets to off
    rather than carrying into the next workspace.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    project_selector = dialog.get_project_selector()
    # The MRU repo seeds the selector asynchronously; wait for it to populate
    # before snapshotting so the retention check below compares the real repo
    # rather than an empty placeholder.
    expect(project_selector).not_to_have_text("")
    repo_before = project_selector.text_content()
    assert repo_before, "project selector should display the seeded repo"
    dialog.get_prompt_textarea().fill("first task")
    # The per-prompt agent settings (incl. plan mode) surface once a prompt is
    # typed. Turn plan mode on for this create so the reset is observable.
    plan_toggle = dialog.get_plan_mode_toggle()
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
    expect(dialog.get_project_selector()).to_have_text(repo_before)
    # Plan mode does NOT carry over: type a second prompt to reveal the agent
    # settings again and confirm the toggle is back off.
    dialog.get_prompt_textarea().fill("second task")
    expect(plan_toggle).to_have_attribute("data-active", "false")


@user_story("to pick the first agent's type with Claude as the default")
def test_agent_type_picker_defaults_to_claude(sculptor_instance_: SculptorInstance) -> None:
    """The agent-type select defaults to Claude and lists the available types.

    The form's first-agent picker reuses the old page's options: Claude (default),
    pi, and Terminal are all offered. (The "no bare Terminal agent type" rule
    applies to the panel-tab add-dropdown, not to this first-agent select —
    verified against the rendered form, which DOES offer Terminal here.)
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()

    # Default trigger label is Claude.
    expect(dialog.get_agent_type_select()).to_contain_text("Claude")

    dialog.get_agent_type_select().click()
    expect(dialog.get_agent_type_option_claude()).to_be_visible()
    expect(dialog.get_agent_type_option_terminal()).to_be_visible()
    # pi is always offered.
    expect(dialog.get_agent_type_option_pi()).to_be_visible()


@user_story("to start typing in the chat immediately after creating a workspace")
def test_chat_input_focused_after_workspace_create(sculptor_instance_: SculptorInstance) -> None:
    """After creating a workspace from the dialog, the chat input holds focus.

    Drives the dialog POM directly rather than ``start_task_and_wait_for_ready``:
    that helper re-focuses the chat input itself (to undo its model-selector
    click), which would mask a missing product-side autofocus.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    task_page = dialog.create_and_wait_for_chat_panel(workspace_name="Focus After Create WS")

    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_focused()


@user_story("to land in the terminal when my first agent is a terminal")
def test_terminal_first_agent_does_not_focus_chat(sculptor_instance_: SculptorInstance) -> None:
    """Creating a workspace whose first agent is a Terminal lands in the terminal
    panel — no chat input is mounted for creation to steal focus into."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    dialog.select_agent_type(ElementIDs.AGENT_TYPE_OPTION_TERMINAL)
    dialog.create(workspace_name="Terminal First WS")

    expect(dialog.get_dialog()).to_have_count(0, timeout=60_000)
    expect(get_agent_terminal_panel(page)).to_be_visible(timeout=60_000)
    # The terminal replaces the chat as the agent's main panel: no chat input
    # exists anywhere on the page.
    expect_terminal_panel_replaces_chat(page)


@user_story("to focus the prompt input with the focus_input keybinding")
def test_focus_input_keybinding_focuses_chat_input(sculptor_instance_: SculptorInstance) -> None:
    """Cmd/Ctrl+I (the ``focus_input`` keybinding) focuses the chat input on a
    workspace page after focus has wandered elsewhere."""
    page = sculptor_instance_.page
    mod_key = get_playwright_modifier_key()

    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Focus Input WS")
    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    blur_page(page)
    expect(chat_input).not_to_be_focused()

    page.keyboard.press(f"{mod_key}+i")
    expect(chat_input).to_be_focused()
