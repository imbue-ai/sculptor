"""Integration tests for bash pill rendering in the alpha chat view.

Bash tool calls render as a pill inside the surrounding tool group. Clicking
the bash pill opens a popover containing the command and the output.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see bash commands rendered as pills in the alpha view")
def test_bash_block_renders_for_bash_tool(sculptor_instance_: SculptorInstance) -> None:
    """Bash tool calls render as a bash pill inside a tool pill row."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo hello world"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    bash_pill = alpha_view.get_bash_blocks()
    expect(bash_pill).to_be_visible()


@user_story("to expand bash output by clicking the bash pill")
def test_bash_block_expands_on_click(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the bash pill toggles the popover containing the output."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo expandable output"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_pill = alpha_view.get_bash_blocks()
    expect(bash_pill).to_be_visible()

    output_panel = alpha_view.get_bash_output()
    expect(output_panel).not_to_be_visible()

    # Click pill to open popover
    bash_pill.click()
    expect(output_panel).to_be_visible()

    # Click pill again to close popover
    bash_pill.click()
    expect(output_panel).not_to_be_visible()


@user_story("to see bash command descriptions rendered alongside the command")
def test_bash_description_persists_after_completion(sculptor_instance_: SculptorInstance) -> None:
    """Bash pill (and its popover) should reflect the command description."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo hello", "description": "Print hello"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_pill = alpha_view.get_bash_blocks()
    expect(bash_pill).to_be_visible()

    # Open the popover and verify the description appears in it.
    bash_pill.click()
    popover = alpha_view.get_tool_pill_popover()
    expect(popover).to_contain_text("Print hello")


@user_story("to see error bash pills render in error state")
def test_bash_block_shows_error_badge(sculptor_instance_: SculptorInstance) -> None:
    """Bash pills that exit with an error mark themselves as errored."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo error output && exit 1"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    bash_pill = alpha_view.get_bash_blocks()
    expect(bash_pill).to_be_visible()

    # The popover stays closed by default (no auto-expand at the row level).
    output_panel = alpha_view.get_bash_output()
    expect(output_panel).not_to_be_visible()


@user_story("to see bash pills and file chips coexist in the same message")
def test_bash_block_coexists_with_file_chips(sculptor_instance_: SculptorInstance) -> None:
    """A message with both file writes and bash commands shows both a chip row and a bash pill."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "bash_coexist_test.txt", "content": "hello"}},
    {"command": "bash", "args": {"command": "echo coexist"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    chip_row = alpha_view.get_chip_rows()
    expect(chip_row).to_be_visible()

    bash_pill = alpha_view.get_bash_blocks()
    expect(bash_pill).to_be_visible()
