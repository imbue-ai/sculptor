"""Advanced integration tests for bash block rendering in the alpha chat view.

Covers command text display, stdout verification, multiple sequential blocks,
ordering with file chips, error output visibility, and collapse toggling.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the command text displayed in the bash block popover")
def test_bash_block_shows_command_text(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the bash pill should open a popover containing the executed command text."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo hello world"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()

    bash_block.click()
    popover = alpha_view.get_tool_pill_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("echo hello world")


@user_story("to verify bash output contains stdout after expanding")
def test_bash_block_output_contains_stdout(sculptor_instance_: SculptorInstance) -> None:
    """Expanding the bash block output panel should show the command stdout."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo output_text_123"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()

    bash_block.click()

    output_panel = alpha_view.get_bash_output()
    expect(output_panel).to_be_visible()
    expect(output_panel).to_contain_text("output_text_123")


@user_story("to see multiple bash blocks rendered in sequence")
def test_multiple_bash_blocks_in_sequence(sculptor_instance_: SculptorInstance) -> None:
    """Three sequential bash commands should produce three separate bash blocks."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "echo first"}},
    {"command": "bash", "args": {"command": "echo second"}},
    {"command": "bash", "args": {"command": "echo third"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_blocks = alpha_view.get_bash_blocks()
    expect(bash_blocks).to_have_count(3)


@user_story("to see bash blocks ordered correctly between file chip rows")
def test_bash_block_between_file_chips(sculptor_instance_: SculptorInstance) -> None:
    """A write_file, bash, write_file sequence renders chip_row, bash_block, chip_row."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "order_before.txt", "content": "before"}},
    {"command": "bash", "args": {"command": "echo between"}},
    {"command": "write_file", "args": {"file_path": "order_after.txt", "content": "after"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    chip_rows = alpha_view.get_chip_rows()
    expect(chip_rows).to_have_count(2)

    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()


@user_story("to see error bash blocks with clickable output")
def test_bash_block_error_shows_output_on_click(sculptor_instance_: SculptorInstance) -> None:
    """A bash block that exits with an error stays collapsed but shows output on click."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo error_marker && exit 1"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()

    output_panel = alpha_view.get_bash_output()
    expect(output_panel).not_to_be_visible()

    bash_block.click()
    expect(output_panel).to_be_visible()
    expect(output_panel).to_contain_text("error_marker")


@user_story("to collapse the bash output panel after expanding it")
def test_bash_block_collapse_after_expand(sculptor_instance_: SculptorInstance) -> None:
    """Clicking to expand then clicking again should collapse, hiding the output."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo collapse_test_output"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()

    output_panel = alpha_view.get_bash_output()
    expect(output_panel).not_to_be_visible()

    bash_block.click()
    expect(output_panel).to_be_visible()
    expect(output_panel).to_contain_text("collapse_test_output")

    bash_block.click()
    expect(output_panel).not_to_be_visible()
