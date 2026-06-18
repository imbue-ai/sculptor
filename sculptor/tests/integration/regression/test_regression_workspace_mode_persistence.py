"""Regression test: Workspace selection mode should persist after creating a workspace.

Bug: When a user selects In-place mode and creates a workspace, the mode selector
resets to "Worktree" (the default) instead of remembering the user's last
selection. The next time the user opens the Add Workspace page, they have to
re-select In-place mode manually.

Expected behavior: The workspace selection mode should persist across workspace
creations so users don't have to re-select their preferred mode every time.

Root cause: The mode state is stored as local component state (useState) with a
hardcoded default of WORKTREE, and is not persisted to localStorage or any
other storage mechanism.

Note: The in-place workspace mode option is gated behind the
``enable_in_place_workspaces`` setting (off by default). This test enables the
flag via the config API so the mode selector exposes the In-place option.
"""

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.task_starter import select_home_page_model
from sculptor.testing.elements.user_config import enable_in_place_workspaces
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.mark.xfail(
    reason="Mode persistence not yet implemented in NewWorkspaceModal (lives in atoms but is not seeded from a per-workspace MRU)"
)
@user_story("to have my workspace selection mode persist when creating multiple workspaces")
def test_workspace_selection_mode_persists_after_workspace_creation(sculptor_instance_: SculptorInstance) -> None:
    """Workspace selection mode should persist after creating a workspace.

    Steps:
    1. Enable the in-place workspaces experimental flag
    2. On the Add Workspace page, switch from Worktree (default) to In-place mode
    3. Create a workspace
    4. Navigate back to the Add Workspace page via the "+" button
    5. Verify the mode selector still shows In-place (not Worktree)
    """
    page = sculptor_instance_.page
    add_ws_page = PlaywrightNewWorkspaceModalPage(page=page)

    # Enable the experimental in-place workspaces flag so the mode selector is visible.
    enable_in_place_workspaces(page)

    # We should already be on the Add Workspace page (cleanup deletes all workspaces).
    expect(add_ws_page.get_submit_button()).to_be_visible()

    # Fill in the workspace name (required field)
    add_ws_page.get_workspace_name_input().fill("In-place test workspace")

    # Switch to In-place mode via the mode selector dropdown.
    add_ws_page.select_mode(ElementIDs.MODE_OPTION_IN_PLACE)

    # Verify In-place mode is selected before creating the workspace
    expect(add_ws_page.get_mode_selector()).to_contain_text("In-place")

    # Create a workspace in In-place mode using the Testing Agent
    select_home_page_model(page, "Testing Agent")

    task_input = add_ws_page.get_task_input()
    expect(task_input).to_have_attribute("contenteditable", "true")
    task_input.click()
    task_input.fill("Hello")

    add_ws_page.submit_and_wait_for_chat_panel()
    task_page = PlaywrightTaskPage(page=page)
    expect(task_page.get_thinking_indicator(), "agent to finish").not_to_be_visible()

    # Navigate back to the Add Workspace page via the "+" button
    expect(add_ws_page.get_add_workspace_button()).to_be_visible()
    add_ws_page.get_add_workspace_button().click()

    expect(add_ws_page.get_submit_button()).to_be_visible()

    # After creating a workspace, the mode selector should still show In-place
    expect(add_ws_page.get_mode_selector()).to_contain_text("In-place")
