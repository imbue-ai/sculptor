"""Integration tests for workspace tab context menu rename functionality."""

from playwright.sync_api import expect

from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to rename a workspace tab via the context menu")
def test_workspace_context_menu_rename(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a workspace tab and selecting Rename allows inline renaming.

    Steps:
    1. Create a workspace
    2. Right-click the workspace tab
    3. Verify the Rename item is visible in the context menu
    4. Click Rename
    5. Verify the inline rename input appears
    6. Type a new name and press Enter
    7. Verify the workspace tab text updates to the new name
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Original Name")

    # Step 2: Right-click the workspace tab.
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)
    workspace_tabs.first.click(button="right")

    # Step 3: Verify the Rename item is visible.
    rename_item = layout.get_tab_context_menu_rename()
    expect(rename_item).to_be_visible()

    # Step 4: Click Rename.
    rename_item.click()

    # Step 5: Verify the inline rename input appears.
    rename_input = layout.get_inline_rename_input()
    expect(rename_input).to_be_visible()

    # Step 6: Clear and type a new name, then press Enter.
    rename_input.fill("Renamed Workspace")
    rename_input.press("Enter")

    # Step 7: Confirm rename input dismissed, then verify tab text updates.
    expect(rename_input).not_to_be_visible()
    expect(workspace_tabs.first).to_have_text("Renamed Workspace")


@user_story("to cancel renaming a workspace tab via Escape")
def test_workspace_context_menu_rename_escape_cancels(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Escape during inline rename cancels and reverts to the original name.

    Steps:
    1. Create a workspace
    2. Right-click workspace tab and click Rename
    3. Type a new name
    4. Press Escape
    5. Verify the tab text reverts to the original name
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Test task", workspace_name="Keep This Name")

    # Step 2: Right-click and click Rename.
    workspace_tabs = layout.get_workspace_tabs()
    workspace_tabs.first.click(button="right")

    rename_item = layout.get_tab_context_menu_rename()
    rename_item.click()

    # Step 3: Type a new name.
    rename_input = layout.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    rename_input.fill("Changed Name")

    # Step 4: Press Escape.
    rename_input.press("Escape")

    # Step 5: Confirm rename input dismissed, then verify tab text reverts.
    expect(rename_input).not_to_be_visible()
    expect(workspace_tabs.first).to_have_text("Keep This Name")
