"""Integration tests for workspace-scoped changes visibility.

These tests verify that the Changes tab in the File Browser shows changes
from ALL agents in a workspace, not just the currently viewed agent.

Background:
- Each workspace shares a single git repository among its agents.
- The Changes tab should reflect the state of the workspace's repo,
  regardless of which agent made the changes.

These tests create a workspace with two agents, have each agent write a
different file, and verify that both files appear in the Changes tab
for BOTH agents.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _enable_review_all_via_settings(page: Page) -> None:
    """Enable the Review All experimental setting via the Settings UI."""
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_review_all()


@user_story("to see all workspace changes regardless of which agent made them")
def test_uncommitted_tab_shows_changes_from_all_agents(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Two agents in one workspace each write a file. Both files should appear
    in the Uncommitted tab for both agents.

    Steps:
    1. Create workspace with agent 1, which writes file_from_agent1.py
    2. Add agent 2 to the same workspace, which writes file_from_agent2.py
    3. View agent 2's Uncommitted tab — should show BOTH files
    4. Switch to agent 1's Uncommitted tab — should also show BOTH files
    """
    page = sculptor_instance_.page

    # Create first agent that writes a file
    task_page = start_task_and_wait_for_ready(
        page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "file_from_agent1.py",
  "content": "def created_by_agent1():\\n    return 'agent1'\\n"
}`""",
        workspace_name="Shared Changes WS",
    )

    # Wait for agent 1 to finish
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Add a second agent to the same workspace
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()

    # Wait for the second agent tab to appear
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Send a task to agent 2 that writes a different file
    task_page_2 = PlaywrightTaskPage(page=page)
    chat_panel_2 = task_page_2.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel_2,
        message="""\
fake_claude:write_file `{
  "file_path": "file_from_agent2.py",
  "content": "def created_by_agent2():\\n    return 'agent2'\\n"
}`""",
    )
    wait_for_completed_message_count(chat_panel=chat_panel_2, expected_message_count=2)

    # --- Assert: Agent 2's Changes panel shows BOTH files ---
    task_page_2.activate_changes_panel(scope="uncommitted")
    changes_tree = task_page_2.get_changes_panel().get_changes_tree()
    expect(changes_tree).to_be_visible()
    expect(changes_tree.get_tree_rows()).to_have_count(2)

    # --- Switch to agent 1 and verify its Changes panel also shows BOTH files ---
    agent_tabs.first.click()

    task_page.activate_changes_panel(scope="uncommitted")
    changes_tree_1 = task_page.get_changes_panel().get_changes_tree()
    expect(changes_tree_1).to_be_visible()
    expect(changes_tree_1.get_tree_rows()).to_have_count(2)


@user_story("to review all workspace changes in the full-screen modal")
def test_review_modal_shows_changes_from_all_agents(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Two agents in one workspace each write a file. The Review All combined
    diff should show both files' diffs.

    Steps:
    1. Create workspace with agent 1, which writes review_file1.py
    2. Add agent 2, which writes review_file2.py
    3. Open Review All — should contain diffs for BOTH files
    """
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    # Create first agent that writes a file
    task_page = start_task_and_wait_for_ready(
        page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "review_file1.py",
  "content": "def from_agent1():\\n    return 1\\n"
}`""",
        workspace_name="Review Modal WS",
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Add a second agent and have it write a different file
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    task_page_2 = PlaywrightTaskPage(page=page)
    chat_panel_2 = task_page_2.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel_2,
        message="""\
fake_claude:write_file `{
  "file_path": "review_file2.py",
  "content": "def from_agent2():\\n    return 2\\n"
}`""",
    )
    wait_for_completed_message_count(chat_panel=chat_panel_2, expected_message_count=2)

    # Switch to Changes tab and click Review All
    task_page_2.activate_changes_panel()
    task_page_2.click_review_all()

    # The diff panel should show both files
    diff_panel = task_page_2.get_diff_panel()
    expect(diff_panel).to_be_visible()
    expect(diff_panel).to_contain_text("review_file1.py")
    expect(diff_panel).to_contain_text("review_file2.py")


@user_story("to see all workspace changes regardless of which agent made them")
def test_uncommitted_tab_updates_when_other_agent_modifies_files(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Agent 1 writes a file, then agent 2 writes a file. When switching back
    to agent 1, its Uncommitted tab should show the file written by agent 2.

    This specifically tests that changes made by other agents are reflected
    without requiring a page refresh or re-navigation.

    Steps:
    1. Create workspace with agent 1, which writes file_a.py
    2. Verify agent 1's Uncommitted tab shows 1 file
    3. Add agent 2, which writes file_b.py
    4. Switch back to agent 1
    5. Agent 1's Uncommitted tab should now show 2 files
    """
    page = sculptor_instance_.page

    # Create first agent that writes a file
    task_page = start_task_and_wait_for_ready(
        page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "file_a.py",
  "content": "a = 1\\n"
}`""",
        workspace_name="Update WS",
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Verify agent 1 initially shows 1 file
    task_page.activate_changes_panel(scope="uncommitted")
    changes_tree = task_page.get_changes_panel().get_changes_tree()
    expect(changes_tree).to_be_visible()
    expect(changes_tree.get_tree_rows()).to_have_count(1)

    # Add second agent and have it write another file
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    task_page_2 = PlaywrightTaskPage(page=page)
    chat_panel_2 = task_page_2.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel_2,
        message="""\
fake_claude:write_file `{
  "file_path": "file_b.py",
  "content": "b = 2\\n"
}`""",
    )
    wait_for_completed_message_count(chat_panel=chat_panel_2, expected_message_count=2)

    # Switch back to agent 1
    agent_tabs.first.click()

    # Agent 1's Changes panel should now show BOTH files
    task_page.activate_changes_panel(scope="uncommitted")
    changes_tree_1 = task_page.get_changes_panel().get_changes_tree()
    expect(changes_tree_1).to_be_visible()
    # This is the key assertion: agent 1 should see agent 2's file too
    expect(changes_tree_1.get_tree_rows()).to_have_count(2)
