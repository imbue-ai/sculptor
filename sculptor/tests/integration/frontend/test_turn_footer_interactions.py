"""Integration tests for turn footer interactions in the alpha chat view.

Verifies that:
1. Clicking the token count opens a popover with token breakdown.
2. Clicking a file in the file changes popover opens the diff panel.
3. The alpha view mode persists when the diff panel opens and closes.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_panel import get_diff_panel_from_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to click the token count in the turn footer and see a breakdown of input/output tokens")
def test_token_popover_shows_breakdown_on_click(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the user clicks on the token count in the turn footer,
    a popover should appear showing input and output token counts.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Hello from assistant."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Turn footer should be visible with token count
    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()
    expect(turn_footers.first).to_contain_text("tokens")

    # Click on the token count to open the popover
    token_count = alpha_view.get_turn_footer_token_count()
    token_count.click()

    # Token popover should appear with "Input" and "Output" labels
    token_popover = alpha_view.get_token_popover()
    expect(token_popover).to_be_visible()
    expect(token_popover).to_contain_text("Input")
    expect(token_popover).to_contain_text("Output")


@user_story("to click a file in the turn footer popover and have it open the diff panel")
def test_file_click_in_popover_opens_diff_panel(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the user clicks on a file in the file changes popover,
    the diff panel should open showing the file's changes.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "popover_click_test.txt",
  "content": "line one\\nline two"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Turn footer should show "1 file"
    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()
    expect(turn_footers.first).to_contain_text("1 file")

    # Click on the file count to open the popover
    file_count_trigger = alpha_view.get_turn_footer_file_count()
    file_count_trigger.click()

    # Wait for popover to show the file row, then click it to open the diff
    file_row = alpha_view.get_turn_footer_file_row()
    expect(file_row).to_be_visible()
    file_row.click()

    # The diff panel should open
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()


@user_story("to keep the alpha view mode when the diff panel opens and closes")
def test_alpha_view_persists_when_diff_panel_opens(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the user is in alpha view mode and opens the diff panel (e.g. via
    turn footer file click), the view mode should stay on alpha, not reset to
    classic. This was a bug where the view mode was stored in useState and
    reset on remount.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "view_persist_test.txt",
  "content": "persist test content"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Open the diff panel via the turn footer's file changes popover
    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()
    expect(turn_footers.first).to_contain_text("1 file")

    file_count_trigger = alpha_view.get_turn_footer_file_count()
    file_count_trigger.click()

    file_row = alpha_view.get_turn_footer_file_row()
    expect(file_row).to_be_visible()
    file_row.click()

    # Diff panel should open
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Alpha view should still be visible (not reset to classic)
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()


@user_story("to see the edit_file tool result show up as a file change in the turn footer")
def test_turn_footer_file_count_after_edit_file(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the agent uses edit_file, the turn footer should show the file
    count, since edit_file produces a diff result.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "edit_test.txt", "content": "original content"}},
    {"command": "edit_file", "args": {"file_path": "edit_test.txt", "old_string": "original", "new_string": "modified"}},
    {"command": "text", "args": {"text": "Done editing."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Turn footer should show file count (1 file, since both operations touch the same file)
    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()
    expect(turn_footers.first).to_contain_text("1 file")
