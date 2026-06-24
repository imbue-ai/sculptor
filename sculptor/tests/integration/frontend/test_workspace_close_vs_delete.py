"""Integration tests for workspace tab close-vs-delete separation.

Tests verify:
- Closing a workspace tab removes the tab without deleting the workspace
- Cmd+W closes the active workspace tab without deletion
- A closed workspace can be reopened from the workspace list
- "Close All" context menu removes all tabs without deleting workspaces
- "Close Others" context menu removes all tabs except the right-clicked one
"""

import json

from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Workspace A")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Workspace B")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(0)

    confirm_dialog = layout.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_hidden()
    expect(workspace_tabs).to_have_count(1)

    navigate_to_home_page(page)

    home_page = PlaywrightHomePage(page)
    workspace_rows = home_page.get_workspace_rows()
    expect(workspace_rows).to_have_count(2)


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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task 1", workspace_name="WS One")
    start_task_and_wait_for_ready(page, prompt="Task 2", workspace_name="WS Two")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")

    confirm_dialog = layout.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_hidden()
    expect(workspace_tabs).to_have_count(1)


@user_story("to delete the active workspace via keyboard shortcut")
def test_cmd_shift_w_deletes_active_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+Shift+W deletes the active workspace after confirmation.

    Unlike Cmd+W (which just closes the tab), Cmd+Shift+W opens the delete
    confirmation dialog; confirming permanently removes the workspace.

    Steps:
    1. Create two workspaces (the second is active)
    2. Press Cmd+Shift+W
    3. Verify the delete confirmation dialog appears
    4. Confirm the deletion and verify the tab count drops to 1
    5. Navigate Home and verify the deleted workspace is gone (proving it was
       deleted, not merely closed — a closed workspace would still be listed)
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # "Delete WS" is active after creation.
    start_task_and_wait_for_ready(page, prompt="Task 1", workspace_name="Keep WS")
    start_task_and_wait_for_ready(page, prompt="Task 2", workspace_name="Delete WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+w")

    # Unlike Cmd+W, this opens the delete confirmation dialog.
    confirm_dialog = layout.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_visible()

    layout.confirm_delete()
    expect(workspace_tabs).to_have_count(1)

    # A closed (not deleted) workspace would still be listed here.
    navigate_to_home_page(page)
    home_page = PlaywrightHomePage(page)
    expect(home_page.get_workspace_rows()).to_have_count(1)
    expect(home_page.get_workspace_rows().filter(has_text="Delete WS")).to_have_count(0)


@user_story("to delete a workspace with Cmd+Shift+W without the dialog flickering shut")
def test_cmd_shift_w_does_not_dismiss_open_delete_dialog(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Cmd+Shift+W must not dismiss an already-open dismissible overlay.

    Regression test for SCU-1575. The page-layout shortcut handler closes an
    open overlay on Cmd+W (so the tab-close chord dismisses a dialog rather
    than closing the Electron window). Cmd+Shift+W is a different chord
    (delete_workspace) that *opens* the delete-confirmation dialog, so it must
    not be treated as a close-overlay gesture.

    Opening the dialog via the context menu (not the racy Cmd+Shift+W path)
    makes the overlay reliably present, so pressing Cmd+Shift+W here
    deterministically checks that the chord leaves the dialog open and
    confirmable.

    Steps:
    1. Create a workspace
    2. Open the delete-confirmation dialog via the right-click context menu
    3. Press Cmd+Shift+W
    4. Verify the dialog is still open (not dismissed) and still deletes
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task", workspace_name="Dialog WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)

    # Open the delete-confirmation dialog deterministically (not via the racy
    # Cmd+Shift+W path) so the overlay is reliably present for step 3.
    layout.open_workspace_tab_context_menu(0)
    delete_item = layout.get_tab_context_menu_delete()
    expect(delete_item).to_be_visible()
    delete_item.click()

    confirm_dialog = layout.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_visible()

    # Press the delete chord while the dialog is open. It must NOT be treated
    # as a "close the open overlay" gesture (only bare Cmd+W is).
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+w")

    expect(confirm_dialog).to_be_visible()
    layout.confirm_delete()
    expect(workspace_tabs).to_have_count(0)


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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Closeable WS")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Remaining WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(0)

    expect(workspace_tabs).to_have_count(1)

    navigate_to_home_page(page)

    home_page = PlaywrightHomePage(page)
    closed_workspace_row = home_page.get_workspace_rows().filter(has_text="Closeable WS")
    expect(closed_workspace_row).to_be_visible()
    closed_workspace_row.click()

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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task X", workspace_name="WS Alpha")
    start_task_and_wait_for_ready(page, prompt="Task Y", workspace_name="WS Beta")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    workspace_tabs.nth(0).click(button="right")

    close_all_item = layout.get_tab_context_menu_close_all()
    expect(close_all_item).to_be_visible()
    close_all_item.click()

    expect(workspace_tabs).to_have_count(0)

    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    expect(add_ws_page.get_workspace_name_input()).to_be_visible()

    navigate_to_home_page(page)
    home_page = PlaywrightHomePage(page)
    expect(home_page.get_workspace_rows()).to_have_count(2)


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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task P", workspace_name="WS First")
    start_task_and_wait_for_ready(page, prompt="Task Q", workspace_name="WS Second")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    workspace_tabs.nth(1).click(button="right")

    close_others_item = layout.get_tab_context_menu_close_others()
    expect(close_others_item).to_be_visible()
    close_others_item.click()

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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Home Reopen WS")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Stay Open WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(0)
    expect(workspace_tabs).to_have_count(1)

    navigate_to_home_page(page)

    home_page = PlaywrightHomePage(page)
    closed_workspace_row = home_page.get_workspace_rows().filter(has_text="Home Reopen WS")
    expect(closed_workspace_row).to_be_visible()
    closed_workspace_row.click()

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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Flappy WS")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Stable WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(0)
    expect(workspace_tabs).to_have_count(1)

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    pill.click()
    dropdown = layout.get_closed_workspaces_dropdown()
    row = dropdown.get_rows()
    expect(row).to_be_visible()
    row.click()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(0)
    expect(workspace_tabs).to_have_count(1)

    # Wait a moment for any WebSocket updates to arrive
    page.wait_for_timeout(2000)

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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Reopen Close A")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Reopen Close B")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    workspace_tabs.nth(0).click(button="right")
    close_all_item = layout.get_tab_context_menu_close_all()
    expect(close_all_item).to_be_visible()
    close_all_item.click()
    expect(workspace_tabs).to_have_count(0)

    # Wait for the Add Workspace page to finish rendering after close-all
    # navigates to it. Its autoFocused workspace name input would otherwise
    # steal focus from the closed-workspaces popover the moment it opens,
    # causing Radix to dismiss the popover mid-click.
    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    expect(add_ws_page.get_workspace_name_input()).to_be_visible()

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("2")
    pill.click()

    dropdown = layout.get_closed_workspaces_dropdown()
    rows = dropdown.get_rows()
    expect(rows).to_have_count(2)
    rows.nth(0).click()
    expect(workspace_tabs).to_have_count(1)

    pill.click()
    rows = dropdown.get_rows()
    expect(rows).to_have_count(1)
    rows.nth(0).click()
    expect(workspace_tabs).to_have_count(2)
    expect(pill).not_to_be_visible()

    layout.close_workspace_tab(0)
    expect(workspace_tabs).to_have_count(1)

    # Wait for any out-of-order WebSocket updates to arrive
    page.wait_for_timeout(3000)

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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Task A", workspace_name="Home Close A")
    start_task_and_wait_for_ready(page, prompt="Task B", workspace_name="Home Close B")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    workspace_tabs.nth(0).click(button="right")
    close_all_item = layout.get_tab_context_menu_close_all()
    expect(close_all_item).to_be_visible()
    close_all_item.click()
    expect(workspace_tabs).to_have_count(0)

    navigate_to_home_page(page)
    home_page = PlaywrightHomePage(page)
    first_row = home_page.get_workspace_rows().filter(has_text="Home Close A")
    expect(first_row).to_be_visible()
    first_row.click()
    expect(workspace_tabs).to_have_count(1)

    navigate_to_home_page(page)
    second_row = home_page.get_workspace_rows().filter(has_text="Home Close B")
    expect(second_row).to_be_visible()
    second_row.click()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(0)
    expect(workspace_tabs).to_have_count(1)

    # Wait for any out-of-order WebSocket updates to arrive
    page.wait_for_timeout(3000)

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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Migrate Open")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="Migrate Closed")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

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

    # The open workspace should have a tab; the closed one should not
    expect(workspace_tabs).to_have_count(1)

    # The closed workspace should appear in the closed workspaces dropdown
    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("1")

    old_key = get_local_storage_item(page, "sculptor-open-workspace-tab-ids")
    assert old_key is None, f"Old localStorage key should have been deleted, but found: {old_key}"
