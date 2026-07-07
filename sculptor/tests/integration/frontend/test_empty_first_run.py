"""Integration tests for the empty first-run experience.

With zero workspaces the app renders the normal shell, and landing on Home
auto-opens the new-workspace dialog with the prompt prefilled to the
``/sculptor:help`` action text — creating a workspace is the home experience
until one exists. The sidebar shows the empty-state "Add a repo" /
"No workspaces yet" affordances, and every create entry point stays live: the
dialog can be dismissed and reopened via the sidebar's New Workspace button or
the Cmd/Meta+T shortcut, and Cmd+K still opens the command palette. Creating
the first workspace navigates to the full workspace page.

These tests need a genuinely zero-workspace instance. The shared
``sculptor_instance_`` already deletes every workspace in its per-test cleanup,
so ``sculptor_instance_empty_first_run_`` routes Home and waits for the
auto-opened dialog before each test.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

HELP_PROMPT_PREFILL = "/sculptor:help I just set up Sculptor for the first time. What should I know to get started?"


@user_story("to be offered the new-workspace dialog when I have no workspaces yet")
def test_empty_state_auto_opens_dialog(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """With zero workspaces, Home auto-opens the new-workspace dialog."""
    page = sculptor_instance_empty_first_run_.page
    dialog = PlaywrightNewWorkspaceDialog(page)

    expect(dialog.get_dialog()).to_be_visible()
    expect(dialog.get_form()).to_be_visible()
    expect(dialog.get_create_button()).to_be_visible()


@user_story("to start my first workspace with the help prompt already filled in")
def test_first_prompt_is_prefilled_with_help(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """The auto-opened dialog's prompt is prefilled with the /sculptor:help text."""
    page = sculptor_instance_empty_first_run_.page
    dialog = PlaywrightNewWorkspaceDialog(page)

    expect(dialog.get_prompt_textarea()).to_have_value(HELP_PROMPT_PREFILL)


@user_story("to see a 'No workspaces yet' hint under my repo before I create anything")
def test_sidebar_shows_no_workspaces_hint(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """With a repo registered but no workspaces, the sidebar shows the hint."""
    page = sculptor_instance_empty_first_run_.page

    expect(page.get_by_test_id(ElementIDs.SIDEBAR_NO_WORKSPACES_HINT)).to_be_visible()


@user_story("to reopen the create dialog from the sidebar after dismissing it")
def test_dismissed_dialog_reopens_via_sidebar_button(
    sculptor_instance_empty_first_run_: SculptorInstance,
) -> None:
    """The sidebar's New Workspace button stays live with zero workspaces.

    Dismissing the auto-opened dialog leaves the empty Home list; the sidebar
    button is the explicit reopen path. The reopened dialog is a plain open —
    the onboarding prefill belongs to the auto-open only.
    """
    page = sculptor_instance_empty_first_run_.page
    dialog = PlaywrightNewWorkspaceDialog(page)

    page.keyboard.press("Escape")
    expect(dialog.get_dialog()).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.ADD_WORKSPACE_EMPTY_STATE)).to_be_visible()

    dialog.open_via_sidebar_button()
    expect(dialog.get_prompt_textarea()).to_have_value("")


@user_story("to use Cmd+K and Cmd/Meta+T before my first workspace exists")
def test_global_shortcuts_live_in_empty_state(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """Cmd+K and the new-workspace shortcut work with zero workspaces.

    The command palette opens on Cmd+K, and Cmd/Meta+T reopens the
    new-workspace dialog after a dismissal — no entry point is gated on the
    first workspace existing.
    """
    page = sculptor_instance_empty_first_run_.page
    dialog = PlaywrightNewWorkspaceDialog(page)
    expect(dialog.get_dialog()).to_be_visible()

    mod_key = get_playwright_modifier_key()

    # Dismiss the auto-opened dialog, then Cmd+K opens the command palette.
    page.keyboard.press("Escape")
    expect(dialog.get_dialog()).to_have_count(0)
    page.keyboard.press(f"{mod_key}+k")
    page.keyboard.up(mod_key)
    command_palette = page.get_by_test_id(ElementIDs.COMMAND_PALETTE)
    expect(command_palette).to_be_visible()
    page.keyboard.press("Escape")
    expect(command_palette).to_have_count(0)

    # Cmd/Meta+T reopens the new-workspace dialog.
    page.keyboard.press(f"{mod_key}+t")
    page.keyboard.up(mod_key)
    expect(dialog.get_dialog()).to_be_visible()


@user_story("to create my first workspace from the auto-opened dialog and land in the full workspace")
def test_creating_first_workspace_navigates_to_workspace(
    sculptor_instance_empty_first_run_: SculptorInstance,
) -> None:
    """Creating the first workspace closes the dialog and shows the workspace page."""
    page = sculptor_instance_empty_first_run_.page
    dialog = PlaywrightNewWorkspaceDialog(page)

    dialog.create_and_wait_for_chat_panel(workspace_name="First WS")

    # A workspace row appears in the sidebar and the empty-state hint is gone.
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(1)
    expect(page.get_by_test_id(ElementIDs.SIDEBAR_NO_WORKSPACES_HINT)).to_have_count(0)
