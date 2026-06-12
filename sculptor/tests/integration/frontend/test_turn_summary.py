"""Integration tests for the turn footer file changes in the alpha chat view.

Verifies that:
1. After a file write, the turn footer shows a file count.
2. After editing multiple files, the turn footer shows a file count.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see file count in the turn footer after a file write")
def test_turn_footer_shows_file_count_after_write_file(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the agent writes a file, the turn footer should display
    a file count alongside duration and token count.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "footer_diff_test_file.txt",
  "content": "hello world"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Turn footer should be visible with file count
    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()

    # Footer should contain "1 file" for the single written file
    expect(turn_footers.first).to_contain_text("1 file")


@user_story("to see turn footer with file count after editing multiple files")
def test_turn_footer_file_count_after_multi_file_edit(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the agent creates multiple files, the turn footer should show
    a file count for all file changes.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "stats_a.txt", "content": "line 1\\nline 2\\nline 3"}},
    {"command": "write_file", "args": {"file_path": "stats_b.txt", "content": "alpha\\nbeta"}},
    {"command": "text", "args": {"text": "Done."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Turn footer should show file count
    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()

    # Footer should contain "2 files" for the two written files
    expect(turn_footers.first).to_contain_text("2 files")

    # Footer should also contain token info
    expect(turn_footers.first).to_contain_text("tokens")
