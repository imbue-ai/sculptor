"""Integration tests for the Home page (/home).

Tests verify:
- Recent workspaces are shown on the home page
- Empty state when no workspaces exist
- Search filters the workspace list
- Clicking a workspace row navigates to that workspace
- Workspace row branch display shows current branch (not source branch)
"""

from playwright.sync_api import expect

from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see my recent workspaces on the home page")
def test_recent_workspaces_shown_on_home_page(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After creating a workspace, navigating to /home should show it in the recent list."""
    page = sculptor_instance_.page

    # Create a workspace
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Build the feature",
        workspace_name="My Feature Workspace",
    )

    # Navigate to Home page
    navigate_to_home_page(page)

    # Wait for the recent workspaces to load and verify the workspace appears
    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="My Feature Workspace")
    expect(workspace_row).to_be_visible()


@user_story("to see helpful guidance when I have no workspaces")
def test_empty_state_shown_for_new_user(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When a user has zero workspaces, the empty state should be shown on the home page."""
    page = sculptor_instance_.page

    # Navigate to the home page
    navigate_to_home_page(page)

    # The empty state heading should be visible
    home_page = PlaywrightHomePage(page)
    expect(home_page.get_empty_state()).to_be_visible()

    # The search bar should NOT be visible
    expect(home_page.get_search_input()).not_to_be_visible()


@user_story("to find a workspace quickly by searching")
def test_workspace_search_filters_list(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Typing in the search bar should filter the workspace list in real time."""
    page = sculptor_instance_.page

    # Create two workspaces with distinct names
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Fix auth bug",
        workspace_name="Auth Bug Fix",
    )

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Add dark mode",
        workspace_name="Dark Mode Feature",
    )

    # Navigate to Home page
    navigate_to_home_page(page)

    # Wait for recent workspaces to load
    home_page = PlaywrightHomePage(page)
    auth_row = home_page.get_workspace_rows().filter(has_text="Auth Bug Fix")
    dark_row = home_page.get_workspace_rows().filter(has_text="Dark Mode Feature")
    expect(auth_row).to_be_visible()
    expect(dark_row).to_be_visible()

    # Type in search bar
    home_page.get_search_input().fill("Auth")

    # Only the matching workspace should be visible
    expect(auth_row).to_be_visible()
    expect(dark_row).not_to_be_visible()


@user_story("to quickly navigate to a workspace from the home page")
def test_clicking_workspace_row_navigates_to_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a workspace row should navigate to that workspace."""
    page = sculptor_instance_.page

    # Create a workspace
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Build feature",
        workspace_name="Navigation Test",
    )

    # Navigate to Home page
    navigate_to_home_page(page)

    # Wait for and click the workspace row
    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="Navigation Test")
    expect(workspace_row).to_be_visible()
    workspace_row.click()

    # Should navigate to the workspace — verify by checking the chat panel appears
    task_page = PlaywrightTaskPage(page)
    expect(task_page.get_chat_panel()).to_be_visible()


@user_story("to navigate to a workspace by clicking it in the recent workspaces list")
def test_clicking_recent_workspace_after_reload_navigates_without_spinner(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a recent workspace after page reload should navigate without an infinite spinner.

    Steps:
    1. Create workspace A
    2. Create workspace B (so there are two workspaces)
    3. Fresh-navigate to clear the in-memory MRU agent cache
    4. Wait for the app to load into the MRU workspace
    5. Navigate to the Home page
    6. Click workspace A's row in the recent workspaces list
    7. Verify the chat panel appears (no infinite spinner)
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace A.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Task for workspace A",
        workspace_name="Workspace Alpha",
    )

    # Step 2: Create workspace B (navigates away from A).
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Task for workspace B",
        workspace_name="Workspace Beta",
    )

    # Step 3: Fresh-navigate to clear in-memory tab state, forcing the
    # rootLoader to rehydrate from persisted storage instead of memory.
    soft_reload_page(page)

    # Step 4: Wait for the app to finish loading after reload.
    # The root loader redirects to the MRU workspace, so the chat panel should appear.
    task_page = PlaywrightTaskPage(page)
    expect(task_page.get_chat_panel()).to_be_visible(timeout=30000)

    # Step 5: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 6: Click workspace A's row in the recent workspaces list.
    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="Workspace Alpha")
    expect(workspace_row).to_be_visible()
    workspace_row.click()

    # Step 7: Verify the chat panel appears — this means the workspace loaded
    # successfully. With the bug, this would time out because an infinite
    # spinner is shown instead.
    expect(task_page.get_chat_panel()).to_be_visible()


@user_story("to see the current branch for each workspace on the home page")
def test_workspace_row_shows_current_branch_not_source_branch(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After an agent switches branches, the workspace row should show the current branch.

    Steps:
    1. Create a workspace whose agent immediately checks out a new branch
    2. Navigate to the Home page
    3. Verify the workspace row shows the new (current) branch, not the source branch
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace. FakeClaude checks out a new branch in the clone.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "git checkout -b feature-xyz"}`',
        workspace_name="Branch Display Test",
    )

    # Step 2: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 3: Find the workspace row and verify it shows the current branch.
    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="Branch Display Test")
    expect(workspace_row).to_be_visible()

    # The branch polling (3-second interval) should have picked up the branch
    # change by now. The workspace row should show "feature-xyz" (the current
    # branch after the agent switched), NOT the source branch.
    branch_element = home_page.get_workspace_row_branch(workspace_row)
    expect(branch_element).to_have_text("feature-xyz")
