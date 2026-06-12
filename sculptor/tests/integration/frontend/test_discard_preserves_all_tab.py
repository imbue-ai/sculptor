"""Regression test: discarding the last uncommitted file must not clear the All tab.

When a workspace has committed changes (visible in the All tab) and uncommitted
changes (visible in the Uncommitted tab), discarding the last uncommitted file
must leave the All tab intact — it should still show the committed files.

Before the fix, useDiscardFile called getWorkspaceDiff without scope="vs-target-branch",
so the response only populated uncommittedDiff (empty after the discard) and wiped out
targetBranchDiff, causing the All tab to show "No changes" until a manual Refresh.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Set up a feature branch with:
#   1. committed.py  — committed to the feature branch (visible in All, not in Uncommitted)
#   2. scratch.py    — written but NOT committed (visible in both All and Uncommitted)
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
        "file_path": "scratch.py",
        "content": "y = 2\\n"
      }
    }
  ]
}`"""


@user_story("to see committed changes in the All tab after discarding the last uncommitted file")
def test_discard_last_uncommitted_keeps_all_tab_populated(sculptor_instance_: SculptorInstance) -> None:
    """Discarding the last uncommitted file must not clear the All tab.

    After discarding scratch.py (the only uncommitted change), the All tab
    should still show committed.py. It should NOT show "No changes".
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_SETUP_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open Changes panel on the Uncommitted scope and verify scratch.py is there
    task_page.activate_changes_panel(scope="uncommitted")
    changes_panel = task_page.get_changes_panel()
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    uncommitted_rows = changes_tree.get_tree_rows()
    expect(uncommitted_rows).to_have_count(1)
    expect(uncommitted_rows.first).to_contain_text("scratch.py")

    # Hover over scratch.py to reveal the discard button, then discard it
    uncommitted_rows.first.hover()
    discard_button = changes_panel.get_discard_button(uncommitted_rows.first)
    expect(discard_button).to_be_visible()
    discard_button.click()

    # Confirm the discard dialog
    dialog = changes_panel.get_discard_dialog()
    expect(dialog).to_be_visible()
    changes_panel.get_discard_dialog_confirm().click()
    expect(dialog).to_be_hidden()

    # After discarding the last uncommitted file, the Uncommitted scope is empty
    expect(uncommitted_rows).to_have_count(0)

    # Switch to the All scope (vs-target-branch) — committed.py must still appear
    all_scope_btn = changes_panel.get_scope_all()
    expect(all_scope_btn).to_be_visible()
    all_scope_btn.click()

    # The All tab must NOT be empty — committed.py should still be visible
    all_tab_tree = changes_panel.get_changes_tree()
    expect(all_tab_tree).to_be_visible()
    all_tab_rows = all_tab_tree.get_tree_rows()
    expect(all_tab_rows).not_to_have_count(0)
    expect(all_tab_rows.filter(has_text="committed.py")).to_have_count(1)
