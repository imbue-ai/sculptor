"""Integration tests for workspace tab enhancements."""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to quickly open the Add Workspace page via keyboard")
def test_cmd_t_opens_new_workspace_page(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+T navigates to the Add Workspace page.

    Creates a workspace first so we're on a task page, then presses
    the shortcut and verifies the Add Workspace form is shown.
    """
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Create a workspace so we have somewhere to navigate from
    start_task_and_wait_for_ready(page, prompt="Setup task", workspace_name="Shortcut WS")

    # Verify we're on the task page (chat panel visible, no workspace name input)
    expect(add_ws_page.get_chat_panel()).to_be_visible()

    # Blur the active element to ensure focus is not trapped in a text input
    # (e.g. the chat input), which could consume the keypress instead of
    # letting it bubble to the app-level shortcut handler.
    blur_active_element(page)

    # Press Cmd+T (or Ctrl+T on Linux)
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+t")

    # Verify the Add Workspace page is shown
    expect(add_ws_page.get_workspace_name_input()).to_be_visible(timeout=60_000)
    expect(add_ws_page.get_submit_button()).to_be_visible()


@user_story("to close the current workspace tab via keyboard without deleting it")
def test_cmd_w_closes_workspace_tab_without_deletion(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+W on an active workspace closes the tab without deleting.

    The workspace should no longer appear as a tab, but should still be
    accessible from the Open Workspace list.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Create two workspaces so closing one still leaves a tab
    start_task_and_wait_for_ready(page, prompt="Task 1", workspace_name="WS One")
    start_task_and_wait_for_ready(page, prompt="Task 2", workspace_name="WS Two")

    # Verify both workspace tabs exist
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # Blur the active element to ensure focus is not trapped in a text input
    blur_active_element(page)

    # Press Cmd+W to close the active tab
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")

    # No delete confirmation dialog should appear
    expect(layout.get_delete_confirmation_dialog()).to_be_hidden()

    # One tab should remain
    expect(workspace_tabs).to_have_count(1)


@user_story("to delete a workspace via the tab context menu")
def test_context_menu_delete_removes_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a workspace tab and selecting Delete triggers deletion.

    Creates a workspace, right-clicks its tab, selects Delete,
    confirms in the dialog, and verifies the workspace is removed.
    """
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Create a workspace
    start_task_and_wait_for_ready(page, prompt="Deletable task", workspace_name="Deletable WS")

    workspace_tabs = add_ws_page.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)

    # Right-click the workspace tab, select Delete, and confirm
    add_ws_page.delete_workspace_via_context_menu()

    # Wait for dialog to close
    expect(add_ws_page.get_delete_confirmation_dialog()).to_be_hidden()

    # Workspace tab should be removed
    expect(workspace_tabs).to_have_count(0)

    # Should be on the Add Workspace page (no workspaces left)
    expect(add_ws_page.get_workspace_name_input()).to_be_visible()


@user_story("to dismiss the Add Workspace page and return to my previous workspace")
def test_new_workspace_tab_x_navigates_to_mru_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking X on the Open Workspace tab navigates back to the MRU workspace.

    Creates a workspace, navigates to Add Workspace via the "+" button,
    then clicks the X on the "Open Workspace" tab and verifies navigation
    back to the original workspace.
    """
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Create a workspace so we have an MRU workspace
    start_task_and_wait_for_ready(page, prompt="MRU task", workspace_name="MRU WS")

    # Verify we're on the task page
    chat_panel = add_ws_page.get_chat_panel()
    expect(chat_panel).to_be_visible()

    # Verify the workspace tab is visible in the tab bar before navigating away.
    # The close button on the Add Workspace tab only renders when there is at
    # least one workspace tab (effectiveOpenTabIds.length > 0 controls
    # alwaysCloseable).  On slow CI runners the WebSocket update with the new
    # workspace may arrive late, so explicitly wait for the workspace tab.
    workspace_tabs = add_ws_page.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1, timeout=30_000)

    # Navigate to Add Workspace page via the "+" button
    add_workspace_button = add_ws_page.get_add_workspace_button()
    expect(add_workspace_button).to_be_visible()
    add_workspace_button.click()

    # Verify we're on the Add Workspace page
    expect(add_ws_page.get_workspace_name_input()).to_be_visible()

    # Find the active "New Workspace" tab and click its close button.
    # The close button is conditionally rendered (not just CSS-hidden) in the
    # default SortableTab variant: it appears when the tab is hovered OR active.
    # Multiple new workspace tabs can exist; target the last one (just opened).
    new_workspace_tab = add_ws_page.get_add_workspace_tabs().last
    expect(new_workspace_tab).to_be_visible(timeout=30_000)
    new_workspace_tab.hover()
    close_button = new_workspace_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    expect(close_button).to_be_visible(timeout=30_000)
    close_button.click()

    # Verify we navigated back to the workspace (chat panel visible)
    expect(chat_panel).to_be_visible()

    # Verify workspace tab is still there
    expect(add_ws_page.get_workspace_tabs()).to_have_count(1)


@user_story("to dismiss the Add Workspace page via keyboard and return to my previous workspace")
def test_cmd_w_on_new_workspace_page_navigates_to_mru_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+W on the Add Workspace page navigates to the MRU workspace.

    This is the keyboard equivalent of clicking the X on the Open Workspace tab.
    """
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Create a workspace so we have an MRU workspace
    start_task_and_wait_for_ready(page, prompt="MRU task", workspace_name="MRU WS 2")

    # Navigate to Add Workspace page via "+" button
    add_ws_page.get_add_workspace_button().click()

    # Verify we're on the Add Workspace page
    expect(add_ws_page.get_workspace_name_input()).to_be_visible()

    # Wait for the workspace tab to appear — this confirms the route change
    # has fully propagated and React effects (including the keydown listener
    # in WorkspaceTabs) have re-attached.
    expect(add_ws_page.get_workspace_tabs()).to_have_count(1, timeout=30_000)

    # Blur the active element to ensure focus is not trapped in the workspace
    # name input, which could consume the keypress.
    blur_active_element(page)

    # Press Cmd+W — should navigate back to MRU workspace, no confirmation.
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")

    # Verify navigation back to the workspace
    expect(add_ws_page.get_chat_panel()).to_be_visible()

    # No delete confirmation dialog should appear
    expect(add_ws_page.get_delete_confirmation_dialog()).to_be_hidden()
