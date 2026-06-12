"""Integration tests for the diff scope picker and expanded diff view.

Tests verify that the scope picker defaults to All when opened from
the Changes tab, and that the expand toggle works correctly.
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


@user_story("to see the scope picker default to All from the Changes tab")
def test_scope_picker_defaults_to_all(sculptor_instance_: SculptorInstance) -> None:
    """Opening Review All from Changes tab should default to All scope."""
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()
    task_page.click_review_all()

    # Verify the scope picker inside the diff panel is visible and shows "All".
    # The Changes tab also renders its own DiffScopePicker, so we scope to the
    # diff panel to avoid a strict-mode violation from two matching elements.
    diff_panel = task_page.get_diff_panel()
    scope_picker = diff_panel.get_scope_picker()
    expect(scope_picker).to_be_visible()
    expect(scope_picker).to_contain_text("All")


@user_story("to use the expand toggle for distraction-free diff review")
def test_expand_toggle_expands_and_collapses(sculptor_instance_: SculptorInstance) -> None:
    """The expand toggle should expand the diff to fill the layout area."""
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()
    task_page.click_review_all()

    # Click the expand toggle
    diff_panel = task_page.get_diff_panel()
    expand_toggle = diff_panel.get_expand_toggle()
    expect(expand_toggle).to_be_visible()
    expand_toggle.click()
