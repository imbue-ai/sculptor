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


@user_story("to have the rename input focused when renaming a workspace via the context menu")
def test_workspace_row_context_menu_rename_focuses_input(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Selecting Rename from the row context menu focuses the inline input.

    The inline input commits/cancels on blur, so it must take focus the instant
    it mounts — otherwise the user cannot type into it. This asserts focus
    explicitly (as the panel-tab rename test does) rather than relying on a
    later ``fill``, which force-focuses the element and would mask a focus loss.

    Steps:
    1. Create a workspace
    2. Right-click the workspace row and click Rename
    3. Verify the inline rename input holds focus
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Focus Me")

    # Step 2: Right-click the row and click Rename.
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(1)
    sidebar.open_row_context_menu(rows.first)
    rename_item = sidebar.get_context_menu_rename()
    expect(rename_item).to_be_visible()
    rename_item.click()

    # Step 3: The inline rename input must appear AND hold focus.
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    expect(rename_input).to_be_focused()


@user_story("to dismiss an in-progress workspace rename by clicking elsewhere")
def test_workspace_row_context_menu_rename_dismisses_on_click_outside(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking outside an in-progress rename closes it and keeps the old name.

    The input dismisses via ``onBlur``, which only fires if it actually held
    focus; a rename that never took focus stays stuck open when the user clicks
    away. Clicking the chat input moves focus out of the rename input without
    unmounting the sidebar row, so ``not_to_be_visible`` reflects the rename
    being dismissed rather than the row disappearing.

    Steps:
    1. Create a workspace
    2. Right-click the row and click Rename (the input takes focus)
    3. Click the chat input (somewhere else)
    4. Verify the rename input is dismissed and the row keeps its original name
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace.
    task_page = start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Leave Me Alone")

    # Step 2: Right-click the row and click Rename.
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(1)
    sidebar.open_row_context_menu(rows.first)
    rename_item = sidebar.get_context_menu_rename()
    expect(rename_item).to_be_visible()
    rename_item.click()
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    expect(rename_input).to_be_focused()

    # Step 3: Click somewhere else — a neutral focusable target that moves focus
    # out of the rename input (firing its blur) without unmounting the row.
    task_page.get_chat_panel().get_chat_input().click()

    # Step 4: The rename input dismisses and the row keeps its original name.
    expect(rename_input).not_to_be_visible()
    expect(sidebar.get_workspace_rows().first).to_contain_text("Leave Me Alone")


@user_story("to have the rename input focused when renaming a workspace via the row dropdown")
def test_workspace_row_dropdown_menu_rename_focuses_input(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Selecting Rename from the row's "..." dropdown focuses the inline input.

    The dropdown renders the same workspace-action menu (and shares the same
    close-time focus handoff) as the right-click context menu, so renaming from
    it must focus the input the same way.

    Steps:
    1. Create a workspace
    2. Open the row's "..." dropdown and click Rename
    3. Verify the inline rename input holds focus
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Dropdown Focus")

    # Step 2: Open the "..." dropdown and click Rename.
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(1)
    sidebar.open_row_dropdown_menu(rows.first)
    rename_item = sidebar.get_context_menu_rename()
    expect(rename_item).to_be_visible()
    rename_item.click()

    # Step 3: The inline rename input must appear AND hold focus.
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    expect(rename_input).to_be_focused()


@user_story("to rename a workspace by double-click and by the menu in the same session")
def test_workspace_row_double_click_and_menu_rename_coexist(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Double-click rename and menu rename share one rename mode and don't interfere.

    Two rename entry points drive the same ``renamingWorkspaceIdAtom``: the row's
    double-click (which sets it directly) and the menu / dropdown (which defers
    through ``pendingWorkspaceRenameIdAtom`` and flushes on the menu's
    ``onCloseAutoFocus``). This exercises both in one session and also covers the
    dropdown's click-outside dismissal.

    Steps:
    1. Create a workspace
    2. Double-click the row — the inline input opens and holds focus; cancel it
    3. Open the "..." dropdown and rename — the input opens and holds focus
    4. Click elsewhere — the dropdown-initiated rename dismisses and the name is kept
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    # Step 1: Create a workspace.
    task_page = start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Coexist WS")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(1)

    # Step 2: Double-click starts a focused rename; Escape cancels it.
    rows.first.dblclick()
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    expect(rename_input).to_be_focused()
    rename_input.press("Escape")
    expect(rename_input).not_to_be_visible()

    # Step 3: The dropdown rename still works right after — focused, not stolen.
    sidebar.open_row_dropdown_menu(sidebar.get_workspace_rows().first)
    rename_item = sidebar.get_context_menu_rename()
    expect(rename_item).to_be_visible()
    rename_item.click()
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    expect(rename_input).to_be_focused()

    # Step 4: Clicking elsewhere dismisses the dropdown-initiated rename.
    task_page.get_chat_panel().get_chat_input().click()
    expect(rename_input).not_to_be_visible()
    expect(sidebar.get_workspace_rows().first).to_contain_text("Coexist WS")
