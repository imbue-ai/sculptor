"""Integration tests for the workspace tab context menu copy actions.

Tests cover:
- Copy workspace name and Copy branch (top-level menu, Rename group)
- Copy workspace id (Diagnostics sub-menu)
copy the correct values to the clipboard.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.clipboard import reset_intercepted_clipboard
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to copy the workspace name, branch, and id from the workspace tab context menu")
def test_workspace_context_menu_copy_name_branch_id(
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
    layout = PlaywrightProjectLayoutPage(page)

    # Step 1: Create a workspace with a known name (the name becomes the
    # workspace description, which is what "Copy workspace name" copies).
    workspace_name = "Copy Targets WS"
    start_task_and_wait_for_ready(page, prompt="Workspace copy test", workspace_name=workspace_name)

    # Step 2: Install clipboard interceptor.
    install_clipboard_interceptor(page)
    expect(layout.get_workspace_tabs()).to_have_count(1)

    # Step 3: Copy workspace name.
    layout.open_workspace_tab_context_menu()
    copy_name = layout.get_copy_workspace_name_item()
    expect(copy_name).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_name.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    copied_name = read_intercepted_clipboard(page)
    assert copied_name == workspace_name, f"Expected {workspace_name!r}, got: {copied_name!r}"

    # Step 4: Copy branch.
    layout.open_workspace_tab_context_menu()
    copy_branch = layout.get_copy_branch_item()
    expect(copy_branch).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_branch.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    branch = read_intercepted_clipboard(page)
    assert branch, "Expected a branch name to be copied to clipboard"

    # Step 5: Copy workspace id from the Diagnostics sub-menu.
    layout.open_workspace_diagnostics_submenu()
    copy_id = layout.get_copy_workspace_id_item()
    expect(copy_id).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_id.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    workspace_id = read_intercepted_clipboard(page)
    assert workspace_id, "Expected a workspace id to be copied to clipboard"
