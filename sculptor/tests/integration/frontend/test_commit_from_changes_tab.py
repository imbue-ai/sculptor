"""Integration tests for committing changes from the Changes tab.

Tests verify that the commit button in the Changes tab sends a commit message
to the agent and the changes panel updates accordingly.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.file_tree import get_changes_tree
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to commit changes using the commit button in the Changes tab")
def test_commit_button_sends_commit_message(sculptor_instance_: SculptorInstance) -> None:
    """The commit button should send the commit prompt to the agent.

    After writing a file, open the Changes tab, click the commit button, and
    verify it sends a message to the agent (which appears in chat).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open Changes tab (Uncommitted scope — commit only applies to uncommitted changes)
    task_page.activate_changes_panel(scope="uncommitted")

    # Verify there's a file in the changes tree
    changes_tree = get_changes_tree(page)
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("hello.py")

    # The commit button should be visible and clickable
    commit_btn = task_page.get_commit_button()
    expect(commit_btn).to_be_visible()
    expect(commit_btn).to_contain_text("Commit 1 change")

    # Click the commit button — this sends the commit prompt to the agent
    commit_btn.click()

    # The agent receives a new message (the commit prompt), making it 4 messages total
    # (user prompt, agent response, commit prompt, agent response)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
