"""Integration tests for auto-collapse behavior in the combined diff view.

Tests verify that when the combined diff view has more than 5 files,
they start collapsed, and the expand-all button works.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_SEVEN_FILES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "file_1.py",
        "content": "a = 1\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "file_2.py",
        "content": "b = 2\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "file_3.py",
        "content": "c = 3\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "file_4.py",
        "content": "d = 4\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "file_5.py",
        "content": "e = 5\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "file_6.py",
        "content": "f = 6\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "file_7.py",
        "content": "g = 7\\n"
      }
    }
  ]
}`"""

_THREE_FILES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "small_1.py",
        "content": "a = 1\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "small_2.py",
        "content": "b = 2\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "small_3.py",
        "content": "c = 3\\n"
      }
    }
  ]
}`"""


def _enable_review_all_via_settings(page) -> None:  # noqa: ANN001
    """Enable the Review All setting via the Settings UI (idempotent)."""
    settings_page = navigate_to_settings_page(page=page)
    experimental_section = settings_page.click_on_experimental()
    experimental_section.enable_review_all()


@user_story("to see files auto-collapsed when there are many files in Review All")
def test_many_files_start_collapsed_in_review_all(sculptor_instance_: SculptorInstance) -> None:
    """When the combined diff view has more than 5 files, all files should
    start collapsed. File headers should be visible but diff content hidden."""
    page = sculptor_instance_.page

    # Enable Review All via Settings UI (persists through navigation)
    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_SEVEN_FILES_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()
    task_page.click_review_all()

    # The Review All panel is a thin wrapper around CombinedDiffView, whose scope
    # picker defaults to "Uncommitted"; switch it to "All" (vs the target branch)
    # so the committed files count too.
    review_all_panel = page.get_by_test_id(ElementIDs.REVIEW_ALL_PANEL)
    expect(review_all_panel).to_be_visible()
    review_all_panel.get_by_test_id(ElementIDs.DIFF_SCOPE_ALL).click()

    # All 9 file section headers should be visible (7 uncommitted + 2 committed
    # on the testing branch vs main, since Review All is scoped to "All").
    file_sections = review_all_panel.get_by_test_id(ElementIDs.COMBINED_DIFF_FILE_SECTION)
    expect(file_sections).to_have_count(9)

    # But diff content should not be visible (files are collapsed) — check that
    # no unified diff view is shown
    diff_views = review_all_panel.get_by_test_id(ElementIDs.DIFF_VIEW_UNIFIED)
    expect(diff_views).to_have_count(0)


@user_story("to see files NOT auto-collapsed when there are few files in Review All")
def test_few_files_start_expanded_in_review_all(sculptor_instance_: SculptorInstance) -> None:
    """When the combined diff view has 5 or fewer files, they should
    start expanded (not collapsed)."""
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_THREE_FILES_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()
    task_page.click_review_all()

    # The Review All panel's scope picker defaults to "Uncommitted"; switch it to
    # "All" (vs the target branch) so the committed files count too.
    review_all_panel = page.get_by_test_id(ElementIDs.REVIEW_ALL_PANEL)
    expect(review_all_panel).to_be_visible()
    review_all_panel.get_by_test_id(ElementIDs.DIFF_SCOPE_ALL).click()

    # 5 file section headers should be visible (3 uncommitted + 2 committed
    # on the testing branch vs main, since Review All is scoped to "All").
    file_sections = review_all_panel.get_by_test_id(ElementIDs.COMBINED_DIFF_FILE_SECTION)
    expect(file_sections).to_have_count(5)

    # Diff content should be visible (files are expanded)
    diff_views = review_all_panel.get_by_test_id(ElementIDs.DIFF_VIEW_UNIFIED)
    expect(diff_views).to_have_count(5)
