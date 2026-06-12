"""Integration tests for Review All button visibility in the panel header.

Tests verify that the Review All button appears when the branch has changes
or commits and is not shown when there are none.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _enable_review_all_via_settings(page: Page) -> None:
    """Enable the Review All experimental setting via the Settings UI."""
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_review_all()


_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to see the Review All button when there are uncommitted changes")
def test_review_all_visible_with_uncommitted_changes(sculptor_instance_: SculptorInstance) -> None:
    """Review All button should be visible when the branch has uncommitted changes."""
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()


@user_story("to see the Review All button when the branch has commits only")
def test_review_all_visible_with_commits_only(sculptor_instance_: SculptorInstance) -> None:
    """Review All button should be visible even when all changes are committed.

    After committing all changes on a feature branch, the button should still
    be visible because the branch has commits relative to the target branch.
    """
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    prompt = """\
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
    }
  ]
}`"""
    task_page = start_task_and_wait_for_ready(page, prompt=prompt)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()


@user_story("to not see the Review All button when starting a fresh workspace")
def test_review_all_hidden_with_no_changes(sculptor_instance_: SculptorInstance) -> None:
    """Review All button should be hidden when there are no changes at all.

    Even with the Review All feature enabled, the button should not appear when
    the workspace has no uncommitted changes and no new commits relative to the
    target branch.

    The workspace clone detects ``origin/main`` as the target branch.  By
    starting from ``main`` (not the ``testing`` branch which has 2 extra
    commits), the workspace has zero divergence and ``hasChangesToReview``
    is false.
    """
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    # Switch the project repo to main so the workspace clone starts from a
    # branch with zero commits relative to the target (origin/main).
    sculptor_instance_.repo.repo.run_command(["git", "checkout", "main"])

    # Create a task with default response (no file changes)
    task_page = start_task_and_wait_for_ready(page, prompt="Do nothing")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_hidden(timeout=60_000)
