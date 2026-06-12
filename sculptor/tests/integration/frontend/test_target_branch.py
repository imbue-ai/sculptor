"""Integration tests for target branch behavior.

Tests verify that:
- The "All" scope button is enabled when the workspace has a target branch.
- The scope picker works and diff content updates when switching scopes.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to see that the All scope button is enabled when a target branch is auto-resolved")
def test_all_scope_enabled_with_auto_resolved_target_branch(sculptor_instance_: SculptorInstance) -> None:
    """The test repo has a 'main' branch, so clone workspaces resolve
    target_branch to 'origin/main'. The All scope button should be enabled."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()

    # The scope picker should be visible with the All button enabled
    changes_panel = task_page.get_changes_panel()
    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_be_visible()
    expect(scope_all).to_be_enabled()


@user_story("to see diff content update when switching to All scope")
def test_switching_to_all_scope_shows_target_branch_diff(sculptor_instance_: SculptorInstance) -> None:
    """Switching to All scope should show the target-branch diff content
    (the uncommitted file as a new addition relative to the target branch)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()

    # Switch to All scope
    changes_panel = task_page.get_changes_panel()
    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_be_visible()
    scope_all.click()

    # The changes tree should show files (hello.py is new relative to target branch)
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.filter(has_text="hello.py")).to_be_visible()
