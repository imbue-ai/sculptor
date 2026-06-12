"""Integration test for 'Close other tabs' in the diff tab context menu.

Verifies that right-clicking a diff tab and selecting 'Close other tabs'
closes all other diff tabs but keeps the right-clicked tab open.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.file_tree import get_changes_tree
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Create a feature branch with 3 uncommitted files so they appear in the Changes tab.
_THREE_FILES_PROMPT = """\
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
        "file_path": "alpha.py",
        "content": "a = 1\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "beta.py",
        "content": "b = 2\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "gamma.py",
        "content": "c = 3\\n"
      }
    }
  ]
}`"""


@user_story("to close other diff tabs via the context menu")
def test_diff_tab_close_others(sculptor_instance_: SculptorInstance) -> None:
    """Right-clicking a diff tab and selecting 'Close other tabs' should close
    all other tabs but keep the right-clicked tab open.

    Steps:
    1. Create a workspace with 3 uncommitted files.
    2. Open the Changes tab and click each file to create 3 diff tabs.
    3. Right-click the second diff tab and select 'Close other tabs'.
    4. Verify only 1 diff tab remains (the one that was right-clicked).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_THREE_FILES_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()

    # Open diff tabs by clicking each file in the changes tree
    changes_tree = get_changes_tree(page)
    tree_rows = changes_tree.get_tree_rows()

    tree_rows.filter(has_text="alpha.py").click()
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    tree_rows.filter(has_text="beta.py").click()
    tree_rows.filter(has_text="gamma.py").click()

    # Verify 3 diff tabs are open
    diff_tabs = diff_panel.get_tabs()
    expect(diff_tabs).to_have_count(3)

    # Right-click the beta.py tab and select 'Close other tabs'
    diff_panel.close_other_tabs_via_context_menu("beta.py")

    # Verify only 1 diff tab remains and it is beta.py
    expect(diff_tabs).to_have_count(1)
    expect(diff_tabs.first).to_contain_text("beta.py")
