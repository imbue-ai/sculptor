"""Regression test: workspace creation mode should persist across workspace creations.

Bug: after a user selected In-place mode and created a workspace, the mode
selector reset to "Worktree" (the default) on the next open, forcing the user
to re-select their preferred mode every time.

The new-workspace form now seeds its mode from the last-used creation settings
(recorded on every successful create), so a non-default mode must survive into
the next form open.

Note: The in-place workspace mode option is gated behind the
``enable_in_place_workspaces`` setting (off by default). This test enables the
flag via the config API so the mode selector exposes the In-place option.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.elements.user_config import enable_in_place_workspaces
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to have my workspace selection mode persist when creating multiple workspaces")
def test_workspace_selection_mode_persists_after_workspace_creation(sculptor_instance_: SculptorInstance) -> None:
    """Workspace creation mode should persist after creating a workspace.

    Steps:
    1. Enable the in-place workspaces experimental flag
    2. In the new-workspace dialog, switch from Worktree (default) to In-place
    3. Create the workspace (promptless)
    4. Reopen the new-workspace form via the sidebar's New Workspace button
    5. Verify the mode selector still shows In-place (not Worktree)
    """
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Enable the experimental in-place workspaces flag so the mode selector
    # offers the In-place option.
    enable_in_place_workspaces(page)

    # Per-test cleanup deletes every workspace; bring up the new-workspace
    # dialog. Its create button only mounts once the form has loaded projects.
    open_new_workspace_form(page)
    expect(add_ws_page.get_submit_button()).to_be_visible(timeout=45_000)

    # Fill in the workspace name (required field)
    add_ws_page.get_workspace_name_input().fill("In-place test workspace")

    # Switch to In-place mode via the mode selector dropdown.
    add_ws_page.select_mode(ElementIDs.MODE_OPTION_IN_PLACE)

    # Verify In-place mode is selected before creating the workspace
    expect(add_ws_page.get_mode_selector()).to_contain_text("In-place")

    # The form carries the `/sculptor:help` onboarding prefill when Home
    # auto-opened it; clear the prompt so the agent is created without a first
    # message (the form has no model selector, so an uncleared prompt would
    # start a turn on the default model).
    add_ws_page.get_task_input().fill("")
    add_ws_page.submit_and_wait_for_chat_panel()

    # Reopen the new-workspace form via the sidebar's New Workspace button (the
    # repo "+" direct-creates and never shows the form).
    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_sidebar_button()

    # The reopened form seeds its mode from the last-used creation settings, so
    # it must still show In-place rather than resetting to the Worktree default.
    expect(dialog.get_mode_selector()).to_contain_text("In-place")
