"""Integration tests for agent tab context menu functionality.

Tests cover:
- Agent tab context menu has Rename and Delete items
- Agent tab inline rename via context menu
- Agent tab Delete via context menu with confirmation
"""

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see agent tab context menu with Rename and Delete items")
def test_agent_context_menu_has_rename_and_delete(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking an agent tab shows Rename and Delete.

    Steps:
    1. Create a workspace with an agent
    2. Add a second agent
    3. Right-click the first agent tab
    4. Verify Rename and Delete items are visible
    """
    page = sculptor_instance_.page
    agent_tab_bar = PlaywrightAgentTabBarElement(page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Agent test", workspace_name="Agent WS")

    # Step 2: Add a second agent.
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Step 3: Right-click the first agent tab.
    agent_tab_bar.open_context_menu(agent_tabs.nth(0))

    # Step 4: Verify Rename and Delete items are visible.
    expect(agent_tab_bar.get_context_menu_rename_item()).to_be_visible()
    expect(agent_tab_bar.get_context_menu_delete_item()).to_be_visible()


@user_story("to rename an agent tab via the context menu")
def test_agent_context_menu_rename(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking an agent tab and selecting Rename allows inline renaming.

    Steps:
    1. Create a workspace
    2. Right-click the agent tab and select Rename
    3. Type a new name and press Enter
    4. Verify the agent tab shows the new name
    """
    page = sculptor_instance_.page
    agent_tab_bar = PlaywrightAgentTabBarElement(page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Agent rename test", workspace_name="Rename WS")

    # Step 2: Right-click agent tab and select Rename.
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)
    agent_tab_bar.open_context_menu(agent_tabs.first)

    agent_tab_bar.get_context_menu_rename_item().click()

    # Step 3: Type a new name and press Enter.
    rename_input = agent_tab_bar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    # Wait for focus to land in the input before filling — React autofocus is
    # async after the context-menu click, and on CI runners fill() has
    # occasionally raced the focus handler and submitted empty.
    expect(rename_input).to_be_focused()
    rename_input.fill("My Custom Agent")
    rename_input.press("Enter")
    expect(rename_input).not_to_be_visible()

    # Step 4: Verify the agent tab shows the new name.
    expect(agent_tabs.first).to_have_text("My Custom Agent")


@user_story("to delete an agent via the context menu")
def test_agent_context_menu_delete(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking an agent tab and selecting Delete shows a confirmation then removes the agent.

    Steps:
    1. Create a workspace and add a second agent
    2. Right-click the first agent tab and select Delete
    3. Confirm in the delete confirmation dialog
    4. Verify only one agent tab remains
    """
    page = sculptor_instance_.page
    agent_tab_bar = PlaywrightAgentTabBarElement(page)

    # Step 1: Create a workspace and add a second agent.
    start_task_and_wait_for_ready(page, prompt="Delete test", workspace_name="Delete WS")

    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Step 2: Right-click the first agent tab and select Delete.
    agent_tab_bar.open_context_menu(agent_tabs.nth(0))
    agent_tab_bar.get_context_menu_delete_item().click()

    # Step 3: Confirm deletion.
    confirm_button = agent_tab_bar.get_delete_confirmation_confirm_button()
    expect(confirm_button).to_be_visible()
    confirm_button.click()

    # Step 4: Verify only one agent tab remains.
    expect(agent_tabs).to_have_count(1)
