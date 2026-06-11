"""Integration tests for workspace tab close-vs-delete separation.

Tests verify:
- Closing a workspace tab removes the tab without deleting the workspace
- Cmd+W closes the active workspace tab without deletion
- A closed workspace can be reopened from the workspace list
- "Close All" context menu removes all tabs without deleting workspaces
- "Close Others" context menu removes all tabs except the right-clicked one
"""

import json
import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import get_local_storage_item
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import remove_local_storage_item
from sculptor.testing.playwright_utils import set_local_storage_items
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to close a workspace tab without deleting the workspace")
def test_close_workspace_tab_removes_tab_without_deletion(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the X button on a workspace tab removes the tab but not the workspace.

    Steps:
    1. Create two workspaces so there are two tabs
    2. Click X on the first workspace tab to close it
    3. Verify no delete confirmation dialog appears and tab count drops to 1
    4. Navigate to the Home page
    5. Verify the closed workspace still appears in the workspace list
    """
    page = sculptor_instance_.page

    # Step 1: Create two workspaces.
    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Workspace A")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Workspace B")

    # Step 2: Verify both workspace tabs exist.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Step 3: Click the first tab to activate it, then click its close button.
    workspace_tabs.nth(0).click()
    close_button = workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    # Step 4: Verify no delete confirmation dialog appears and tab count drops to 1.
    confirm_dialog = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)
    expect(confirm_dialog).to_be_hidden()
    expect(workspace_tabs).to_have_count(1)

    # Step 5: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 6: Verify the closed workspace still exists in the workspace list.
    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)
    expect(workspace_rows).to_have_count(2, timeout=10000)


@user_story("to close the active workspace tab via keyboard shortcut")
def test_cmd_w_closes_workspace_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+W closes the active workspace tab without deleting it.

    Steps:
    1. Create two workspaces
    2. Press Cmd+W to close the active tab
    3. Verify no delete confirmation dialog appears and tab count drops to 1
    """
    page = sculptor_instance_.page

    # Step 1: Create two workspaces.
    start_task_and_wait_for_ready(page, prompt="Task 1", workspace_name="WS One")
    start_task_and_wait_for_ready(page, prompt="Task 2", workspace_name="WS Two")

    # Step 2: Verify both workspace tabs exist.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Step 3: Press Cmd+W to close the active tab.
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")

    # Step 4: Verify no delete confirmation dialog appears and tab count drops to 1.
    confirm_dialog = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)
    expect(confirm_dialog).to_be_hidden()
    expect(workspace_tabs).to_have_count(1)


@user_story("to reopen a previously closed workspace from the workspace list")
def test_reopen_closed_workspace_from_list(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Closing a workspace tab and then clicking it in the workspace list reopens it.

    Steps:
    1. Create two workspaces
    2. Close the first workspace tab via the X button
    3. Navigate to the Home page
    4. Click the closed workspace in the workspace list
    5. Verify tab count goes back to 2
    """
    page = sculptor_instance_.page

    # Step 1: Create two workspaces.
    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Closeable WS")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Remaining WS")

    # Step 2: Verify both workspace tabs exist.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Step 3: Close the first workspace tab.
    workspace_tabs.nth(0).click()
    close_button = workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    # Step 4: Verify tab count drops to 1.
    expect(workspace_tabs).to_have_count(1)

    # Step 5: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 6: Find the closed workspace in the list and click it.
    closed_workspace_row = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).filter(has_text="Closeable WS")
    expect(closed_workspace_row).to_be_visible(timeout=10000)
    closed_workspace_row.click()

    # Step 7: Verify tab count goes back to 2.
    expect(workspace_tabs).to_have_count(2)


@user_story("to close all workspace tabs at once via the context menu")
def test_close_all_workspace_tabs_via_context_menu(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a tab and selecting 'Close All' removes all tabs without deletion.

    Steps:
    1. Create two workspaces
    2. Right-click one workspace tab
    3. Click the 'Close All' context menu item
    4. Verify all workspace tabs are gone and the Add Workspace page is shown
    5. Navigate to the Home page and verify both workspaces still exist
    """
    page = sculptor_instance_.page

    # Step 1: Create two workspaces.
    start_task_and_wait_for_ready(page, prompt="Task X", workspace_name="WS Alpha")
    start_task_and_wait_for_ready(page, prompt="Task Y", workspace_name="WS Beta")

    # Step 2: Verify both workspace tabs exist.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Step 3: Right-click one workspace tab to open the context menu.
    workspace_tabs.nth(0).click(button="right")

    # Step 4: Click the 'Close All' item in the context menu.
    close_all_item = page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_ALL)
    expect(close_all_item).to_be_visible()
    close_all_item.click()

    # Step 5: Verify all workspace tabs are gone.
    expect(workspace_tabs).to_have_count(0)

    # Step 6: Close-all in the modal flow lands the user on /home (the
    # old flow rendered the new-workspace form inline; the new flow
    # leaves the user on /home with the topbar + ready). Verify the
    # workspaces still exist by checking the home-page rows.
    expect(page).to_have_url(re.compile(r".*#/home$"))
    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)
    expect(workspace_rows).to_have_count(2, timeout=10000)


@user_story("to close all other workspace tabs except the selected one")
def test_close_others_workspace_tabs_via_context_menu(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a tab and selecting 'Close Others' keeps only the right-clicked tab.

    Steps:
    1. Create two workspaces
    2. Right-click the second workspace tab
    3. Click the 'Close Others' context menu item
    4. Verify only 1 workspace tab remains
    """
    page = sculptor_instance_.page

    # Step 1: Create two workspaces.
    start_task_and_wait_for_ready(page, prompt="Task P", workspace_name="WS First")
    start_task_and_wait_for_ready(page, prompt="Task Q", workspace_name="WS Second")

    # Step 2: Verify both workspace tabs exist.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Step 3: Right-click the second workspace tab to open the context menu.
    workspace_tabs.nth(1).click(button="right")

    # Step 4: Click the 'Close Others' item in the context menu.
    close_others_item = page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_OTHERS)
    expect(close_others_item).to_be_visible()
    close_others_item.click()

    # Step 5: Verify only 1 workspace tab remains.
    expect(workspace_tabs).to_have_count(1)


@user_story("to reopen a closed workspace from the Home page")
def test_reopen_closed_workspace_from_home_page(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Closing a workspace and clicking it on the Home page creates a tab for it.

    Steps:
    1. Create two workspaces
    2. Close the first workspace tab
    3. Navigate to the Home page
    4. Click the closed workspace in the list
    5. Verify tab count goes back to 2
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Home Reopen WS")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Stay Open WS")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Close the first workspace tab
    workspace_tabs.nth(0).click()
    close_button = workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()
    expect(workspace_tabs).to_have_count(1)

    # Navigate to Home page
    navigate_to_home_page(page)

    # Click the closed workspace in the list
    closed_workspace_row = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).filter(has_text="Home Reopen WS")
    expect(closed_workspace_row).to_be_visible(timeout=10000)
    closed_workspace_row.click()

    # Verify tab count goes back to 2
    expect(workspace_tabs).to_have_count(2)


@user_story("to close a workspace and have it stay closed")
def test_closed_workspace_stays_closed(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Closing a workspace from the dropdown should keep it closed permanently.

    Regression test: WebSocket updates must not revert optimistic close operations.

    Steps:
    1. Create two workspaces
    2. Close one workspace
    3. Reopen it from the closed workspaces dropdown
    4. Close it again
    5. Wait briefly for any WebSocket updates
    6. Verify the workspace stays closed (tab count remains 1)
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Flappy WS")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Stable WS")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Close the first workspace
    workspace_tabs.nth(0).click()
    close_button = workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()
    expect(workspace_tabs).to_have_count(1)

    # Reopen from the closed workspaces dropdown
    pill = page.get_by_test_id(ElementIDs.CLOSED_WORKSPACES_PILL)
    expect(pill).to_be_visible()
    pill.click()
    row = page.get_by_test_id(ElementIDs.CLOSED_WORKSPACE_ROW)
    expect(row).to_be_visible()
    row.click()
    expect(workspace_tabs).to_have_count(2)

    # Close it again
    workspace_tabs.nth(0).click()
    close_button = workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()
    expect(workspace_tabs).to_have_count(1)

    # Wait a moment for any WebSocket updates to arrive
    page.wait_for_timeout(2000)

    # Verify the workspace stays closed — tab count should still be 1
    expect(workspace_tabs).to_have_count(1)


@user_story("to close a workspace after reopening from the Home page")
def test_close_after_reopen_from_home_page(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Closing a workspace that was reopened from the Home page should stick.

    Regression test: out-of-order HTTP responses from previous open PATCHes
    must not revert a subsequent close operation.

    Steps:
    1. Create two workspaces
    2. Close both via context menu "Close All"
    3. Reopen first from the closed workspaces dropdown
    4. Reopen second from the closed workspaces dropdown
    5. Close one workspace
    6. Wait for WebSocket updates
    7. Verify the workspace stays closed
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Reopen Close A")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Reopen Close B")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Close both workspaces via context menu "Close All"
    workspace_tabs.nth(0).click(button="right")
    close_all_item = page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_ALL)
    expect(close_all_item).to_be_visible()
    close_all_item.click()
    expect(workspace_tabs).to_have_count(0)

    # Reopen both from the closed workspaces dropdown
    pill = page.get_by_test_id(ElementIDs.CLOSED_WORKSPACES_PILL)
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("2")
    pill.click()

    rows = page.get_by_test_id(ElementIDs.CLOSED_WORKSPACE_ROW)
    expect(rows).to_have_count(2)
    rows.nth(0).click()
    expect(workspace_tabs).to_have_count(1)

    pill.click()
    rows = page.get_by_test_id(ElementIDs.CLOSED_WORKSPACE_ROW)
    expect(rows).to_have_count(1)
    rows.nth(0).click()
    expect(workspace_tabs).to_have_count(2)
    expect(pill).not_to_be_visible()

    # Close one workspace
    workspace_tabs.nth(0).click()
    workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON).click()
    expect(workspace_tabs).to_have_count(1)

    # Wait for any out-of-order WebSocket updates to arrive
    page.wait_for_timeout(3000)

    # Verify the workspace stays closed — dropdown path
    expect(workspace_tabs).to_have_count(1)


@user_story("to close a workspace after reopening it from the Home page")
def test_close_after_reopen_from_home(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Closing a workspace that was reopened from the Home page should stick.

    Regression test: convertHomeTabToWorkspaceAtom must set is_open=true
    and register a pending entry so that out-of-order WebSocket responses
    don't revert the subsequent close.

    Steps:
    1. Create two workspaces
    2. Close both via "Close All" context menu
    3. Reopen both from the Home page
    4. Close one workspace
    5. Wait for WebSocket updates
    6. Verify the workspace stays closed
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Home Close A")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Home Close B")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Close both workspaces via context menu "Close All"
    workspace_tabs.nth(0).click(button="right")
    close_all_item = page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_ALL)
    expect(close_all_item).to_be_visible()
    close_all_item.click()
    expect(workspace_tabs).to_have_count(0)

    # Reopen the first workspace from the Home page
    navigate_to_home_page(page)
    first_row = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).filter(has_text="Home Close A")
    expect(first_row).to_be_visible(timeout=10000)
    first_row.click()
    expect(workspace_tabs).to_have_count(1)

    # Reopen the second workspace from the Home page
    navigate_to_home_page(page)
    second_row = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).filter(has_text="Home Close B")
    expect(second_row).to_be_visible(timeout=10000)
    second_row.click()
    expect(workspace_tabs).to_have_count(2)

    # Close one workspace
    workspace_tabs.nth(0).click()
    workspace_tabs.nth(0).get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON).click()
    expect(workspace_tabs).to_have_count(1)

    # Wait for any out-of-order WebSocket updates to arrive
    page.wait_for_timeout(3000)

    # Verify the workspace stays closed — Home page path
    expect(workspace_tabs).to_have_count(1)


@user_story("to preserve my open/closed workspace state when upgrading to backend tracking")
def test_localstorage_migration_preserves_closed_state(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Simulates an upgrade from localStorage-based to backend-based open/closed tracking.

    The migration reads the old localStorage key, determines which workspaces
    were closed, sends a batch PATCH to close them on the backend, and deletes
    the old key.

    Steps:
    1. Create two workspaces (both open by default)
    2. Get their workspace IDs from the DOM
    3. Set old localStorage key with only ONE workspace ID (simulating a user
       who had closed the other)
    4. Remove new tab-order key so migration triggers on reload
    5. Reload the page
    6. Verify the "closed" workspace appears in the closed dropdown
    7. Verify the old localStorage key was deleted
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Migrate Open")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="Migrate Closed")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(2)

    # Get workspace IDs from tab elements
    open_ws_id = workspace_tabs.nth(0).get_attribute("data-tab-id")
    closed_ws_id = workspace_tabs.nth(1).get_attribute("data-tab-id")
    assert open_ws_id is not None
    assert closed_ws_id is not None

    # Simulate old localStorage state: only the first workspace was "open"
    set_local_storage_items(
        page,
        {
            "sculptor-open-workspace-tab-ids": json.dumps([open_ws_id]),
        },
    )
    # Remove the new tab-order key so the migration path triggers
    remove_local_storage_item(page, "sculptor-tab-order")

    # Full reload to reinitialize all Jotai atoms — migration runs during hydration.
    # Using page.reload() instead of soft_reload_page() because the migration
    # requires a completely fresh atom store (hasHydratedWorkspaceTabsAtom must
    # start as false).
    page.reload()

    # Wait for migration to complete — the batch PATCH needs time to process
    page.wait_for_timeout(2000)

    # The open workspace should have a tab; the closed one should not
    expect(workspace_tabs).to_have_count(1, timeout=10000)

    # The closed workspace should appear in the closed workspaces dropdown
    pill = page.get_by_test_id(ElementIDs.CLOSED_WORKSPACES_PILL)
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("1")

    # The old localStorage key should have been deleted
    old_key = get_local_storage_item(page, "sculptor-open-workspace-tab-ids")
    assert old_key is None, f"Old localStorage key should have been deleted, but found: {old_key}"
