"""Integration tests for exiting expanded diff view with the Escape key.

Tests verify that pressing Escape while in expand mode exits back to the
normal layout.
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
    experimental_settings = settings_page.click_on_experimental()
    experimental_settings.enable_review_all()


_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to exit expanded diff view by pressing Escape")
def test_escape_exits_expand_mode(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Escape in expand mode should return to the normal layout."""
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open Changes tab and click Review All
    task_page.activate_changes_panel()
    task_page.click_review_all()

    # Click expand toggle to enter expand mode
    diff_panel = task_page.get_diff_panel()
    expand_toggle = diff_panel.get_expand_toggle()
    expect(expand_toggle).to_be_visible()
    expand_toggle.click()

    # The chat panel should be hidden in expand mode
    expect(chat_panel).to_be_hidden()

    # Press Escape to exit expand mode
    page.keyboard.press("Escape")

    # The chat panel should be visible again after exiting expand mode
    expect(chat_panel).to_be_visible()
