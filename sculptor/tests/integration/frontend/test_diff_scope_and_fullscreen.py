"""Integration tests for the Review All combined-diff scope picker.

Tests verify that the scope picker in the Review All panel defaults to All.
The diff-specific expand/fullscreen control was removed in the section shell
(section maximize replaces it), so its tests are gone.
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


@user_story("to see the scope picker default to All in the Review All panel")
def test_scope_picker_defaults_to_all(sculptor_instance_: SculptorInstance) -> None:
    """Opening Review All should default its combined-diff scope to All."""
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()
    task_page.click_review_all()

    # The combined diff lives in the Review All panel (the Changes panel renders
    # its own scope picker too), so go through the Review All panel POM to avoid
    # matching two pickers.
    scope_picker = task_page.get_review_all_panel().get_scope_picker()
    expect(scope_picker).to_be_visible()
    expect(scope_picker).to_contain_text("All")
