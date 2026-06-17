"""Integration tests for workspace tab enhancements.

Tests cover:
- Cmd+T keyboard shortcut opens the new-workspace modal
- Cmd+W keyboard shortcut closes the current workspace tab (removes tab, no deletion)
- X button on the Open Workspace tab navigates to the MRU workspace
- Context menu Delete action triggers deletion with confirmation
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to quickly open the new-workspace modal via keyboard")
def test_cmd_t_opens_new_workspace_modal(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+T opens the new-workspace modal.

    Creates a workspace first so we're on a task page, then presses
    the shortcut and verifies the new-workspace form is shown.
    """
    page = sculptor_instance_.page
    modal = PlaywrightNewWorkspaceModalPage(page=page)

    # Create a workspace so we have somewhere to navigate from
    start_task_and_wait_for_ready(page, prompt="Setup task", workspace_name="Shortcut WS")

    # Verify we're on the task page (chat panel visible, no workspace name input)
    chat_panel = modal.get_chat_panel()
    expect(chat_panel).to_be_visible()

    # Blur the active element to ensure focus is not trapped in a text input
    # (e.g. the chat input), which could consume the keypress instead of
    # letting it bubble to the app-level shortcut handler.
    blur_active_element(page)

    # Press Cmd+T (or Ctrl+T on Linux)
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+t")

    # Verify the new-workspace modal is shown
    workspace_name_input = modal.get_workspace_name_input()
    expect(workspace_name_input).to_be_visible(timeout=60_000)

    submit_button = modal.get_submit_button()
    expect(submit_button).to_be_visible()


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
    confirm_dialog = layout.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_hidden()

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
    layout = PlaywrightProjectLayoutPage(page=page)

    # Create a workspace
    start_task_and_wait_for_ready(page, prompt="Deletable task", workspace_name="Deletable WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)

    # Right-click the workspace tab to open the context menu
    workspace_tabs.first.click(button="right")

    # Click the Delete item in the context menu
    delete_item = layout.get_tab_context_menu_delete()
    expect(delete_item).to_be_visible()
    delete_item.click()

    # Confirm the deletion
    confirm_button = layout.get_delete_confirmation_dialog().get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
    expect(confirm_button).to_be_visible()
    confirm_button.click()

    # Wait for dialog to close
    expect(layout.get_delete_confirmation_dialog()).to_be_hidden()

    # Workspace tab should be removed
    expect(workspace_tabs).to_have_count(0)

    # In the modal flow, deleting the last workspace lands the user on
    # /home (the old flow redirected to /ws/new with the form rendered).
    expect(page).to_have_url(re.compile(r".*#/home"))


@user_story("to dismiss the new-workspace modal via keyboard and return to my previous workspace")
def test_cmd_w_on_new_workspace_modal_returns_to_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+W with the new-workspace modal open closes the modal.

    The previous "X on the Open Workspace tab" affordance is gone with the
    modal migration (no pseudo-tab in the bar); Cmd+W is the keyboard
    equivalent — usePageLayoutKeyboardShortcuts re-routes Cmd+W to Esc
    while a dismissible overlay is open.
    """
    page = sculptor_instance_.page
    modal = PlaywrightNewWorkspaceModalPage(page=page)

    # Create a workspace so we have somewhere to return to.
    start_task_and_wait_for_ready(page, prompt="MRU task", workspace_name="MRU WS")

    # Verify we're on the task page
    chat_panel = modal.get_chat_panel()
    expect(chat_panel).to_be_visible()

    # Open the new-workspace modal via the "+" button
    add_workspace_button = modal.get_add_workspace_button()
    add_workspace_button.click()

    # Verify the modal is open
    workspace_name_input = modal.get_workspace_name_input()
    expect(workspace_name_input).to_be_visible()

    # Press Cmd+W — should close the modal, leaving us on the workspace page.
    # Don't blur first: focus is inside the modal's name input and we want to
    # verify the global handler still fires (the suppression branch in
    # usePageLayoutKeyboardShortcuts re-dispatches Esc for Cmd+W when an
    # overlay is open).
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")
    # macOS Chromium can drop the modifier keyup after a chord, leaving the
    # modifier "held"; release it explicitly so the re-dispatched Esc lands as
    # a plain key instead of a modified one.
    page.keyboard.up(mod_key)
    expect(workspace_name_input).to_be_hidden()

    # We should be back on the workspace page
    expect(chat_panel).to_be_visible()

    # No delete confirmation dialog should appear
    confirm_dialog = modal.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_hidden()
