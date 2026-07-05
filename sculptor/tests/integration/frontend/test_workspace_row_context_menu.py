"""Integration tests for the workspace-row context menu.

The workspace tab strip is gone; a workspace's actions now live on its sidebar
row. Right-clicking a row (or opening its "..." dropdown) exposes the shared
workspace-action menu — Rename, the copy group (name / branch), and the
Diagnostics sub-menu (copy id). These rebuild the old
``test_workspace_tab_context_menu_icons`` (rename + Escape cancel) and
``test_workspace_diagnostics_context_menu`` (copy name / branch / id) against the
sidebar row.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.clipboard import reset_intercepted_clipboard
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to rename a workspace via the sidebar-row context menu")
def test_workspace_row_context_menu_rename(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a workspace row and selecting Rename allows inline renaming.

    Steps:
    1. Create a workspace
    2. Right-click the workspace row
    3. Verify the Rename item is visible in the context menu
    4. Click Rename
    5. Verify the inline rename input appears
    6. Type a new name and press Enter
    7. Verify the workspace row text updates to the new name
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Original Name")

    # Step 2: Right-click the workspace row.
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(1)
    sidebar.open_row_context_menu(rows.first)

    # Step 3: Verify the Rename item is visible.
    rename_item = sidebar.get_context_menu_rename()
    expect(rename_item).to_be_visible()

    # Step 4: Click Rename.
    rename_item.click()

    # Step 5: Verify the inline rename input appears.
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()

    # Step 6: Clear and type a new name, then press Enter.
    rename_input.fill("Renamed Workspace")
    rename_input.press("Enter")

    # Step 7: Confirm rename input dismissed, then verify row text updates.
    expect(rename_input).not_to_be_visible()
    expect(sidebar.get_workspace_rows().first).to_contain_text("Renamed Workspace")


@user_story("to cancel renaming a workspace via Escape")
def test_workspace_row_context_menu_rename_escape_cancels(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Escape during inline rename cancels and reverts to the original name.

    Steps:
    1. Create a workspace
    2. Right-click the workspace row and click Rename
    3. Type a new name
    4. Press Escape
    5. Verify the row text reverts to the original name
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Keep This Name")

    # Step 2: Right-click and click Rename.
    sidebar.open_row_context_menu(sidebar.get_workspace_rows().first)
    rename_item = sidebar.get_context_menu_rename()
    rename_item.click()

    # Step 3: Type a new name.
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    rename_input.fill("Changed Name")

    # Step 4: Press Escape.
    rename_input.press("Escape")

    # Step 5: Confirm rename input dismissed, then verify row text reverts.
    expect(rename_input).not_to_be_visible()
    expect(sidebar.get_workspace_rows().first).to_contain_text("Keep This Name")


@user_story("to copy the workspace name, branch, and id from the sidebar-row context menu")
def test_workspace_row_context_menu_copy_name_branch_id(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the workspace copy items copies the correct values to the clipboard.

    Steps:
    1. Create a workspace with a known name
    2. Install clipboard interceptor
    3. Copy workspace name and verify it matches the name the workspace was created with
    4. Copy branch and verify a non-empty value was copied
    5. Copy workspace id (Diagnostics sub-menu) and verify a non-empty value was copied
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace with a known name (the name becomes the
    # workspace description, which is what "Copy workspace name" copies).
    workspace_name = "Copy Targets WS"
    start_task_and_wait_for_ready(page, prompt="Workspace copy test", workspace_name=workspace_name)

    # Step 2: Install clipboard interceptor.
    install_clipboard_interceptor(page)
    expect(sidebar.get_workspace_rows()).to_have_count(1)

    # Step 3: Copy workspace name.
    sidebar.open_row_context_menu(sidebar.get_workspace_rows().first)
    copy_name = sidebar.get_copy_workspace_name_item()
    expect(copy_name).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_name.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    copied_name = read_intercepted_clipboard(page)
    assert copied_name == workspace_name, f"Expected {workspace_name!r}, got: {copied_name!r}"

    # Step 4: Copy branch.
    sidebar.open_row_context_menu(sidebar.get_workspace_rows().first)
    copy_branch = sidebar.get_copy_branch_item()
    expect(copy_branch).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_branch.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    branch = read_intercepted_clipboard(page)
    assert branch, "Expected a branch name to be copied to clipboard"

    # Step 5: Copy workspace id from the Diagnostics sub-menu.
    sidebar.open_diagnostics_submenu(sidebar.get_workspace_rows().first)
    copy_id = sidebar.get_copy_workspace_id_item()
    expect(copy_id).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_id.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    workspace_id = read_intercepted_clipboard(page)
    assert workspace_id, "Expected a workspace id to be copied to clipboard"
