"""Integration tests for File Browser tab switching.

Tests verify that clicking between All, Changes, and History tabs renders
the correct content in each tab.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Create a feature branch, write a file, and commit it so we have content in
# all three tabs: the file tree (All), uncommitted changes (Changes), and
# commit history (History).
_SETUP_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "committed.py",
        "content": "x = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add committed.py'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "uncommitted.py",
        "content": "y = 2\\n"
      }
    }
  ]
}`"""


@user_story("to switch between All, Changes, and History tabs and see correct content")
def test_tab_switching_shows_correct_content(sculptor_instance_: SculptorInstance) -> None:
    """Clicking each tab should display the appropriate content.

    - All tab: shows the file tree with both committed.py and uncommitted.py
    - Changes tab: shows only uncommitted.py
    - History tab: shows commit history with "Add committed.py"
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_SETUP_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    all_tab = file_browser.get_tab_all()
    history_tab = file_browser.get_tab_history()

    # -- All tab: file tree should show both files --
    expect(all_tab).to_be_visible()
    all_tab.click()
    expect(file_browser).to_contain_text("committed.py")
    expect(file_browser).to_contain_text("uncommitted.py")

    # -- Changes tab (Uncommitted scope): only uncommitted.py --
    task_page.activate_changes_panel(scope="uncommitted")
    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("uncommitted.py")

    # -- History tab: shows the commit --
    history_tab.click()
    history_panel = file_browser.get_history_panel()
    expect(history_panel).to_be_visible()
    expect(history_panel).to_contain_text("Add committed.py")

    # -- Switch back to All tab: file tree still works --
    all_tab.click()
    expect(file_browser).to_contain_text("committed.py")
    expect(file_browser).to_contain_text("uncommitted.py")
