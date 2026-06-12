"""Integration tests for cross-feature (mixed tool) scenarios in the alpha chat view.

When a single assistant message contains a mix of tool types — file writes,
bash commands, edits — the alpha view should render each with the correct
component (chip rows for file ops, bash blocks for shell commands).
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see both chip rows and bash blocks when tools are mixed")
def test_mixed_write_bash_read_renders_all_types(sculptor_instance_: SculptorInstance) -> None:
    """A write_file followed by a bash command renders both a chip row and a bash block."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "mixed_test.txt", "content": "hello mixed"}},
    {"command": "bash", "args": {"command": "echo mixed output"}},
    {"command": "text", "args": {"text": "All done with the mixed workflow."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Chip row for the write_file
    chip_row = alpha_view.get_chip_rows()
    expect(chip_row).to_be_visible()

    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_contain_text("mixed_test.txt")

    # Bash block for the echo command
    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()


@user_story("to see multiple chip rows and bash blocks in a complex workflow")
def test_complex_workflow_file_operations(sculptor_instance_: SculptorInstance) -> None:
    """Multiple writes separated by a bash command produce at least 2 chip rows and 1 bash block."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "complex_a.txt", "content": "a"}},
    {"command": "write_file", "args": {"file_path": "complex_b.txt", "content": "b"}},
    {"command": "bash", "args": {"command": "ls"}},
    {"command": "write_file", "args": {"file_path": "complex_c.txt", "content": "c"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)

    # At least 2 chip rows (writes A+B before bash, write C after bash)
    chip_rows = alpha_view.get_chip_rows()
    expect(chip_rows).to_have_count(3)

    # At least 1 bash block
    bash_blocks = alpha_view.get_bash_blocks()
    expect(bash_blocks).to_have_count(1)


@user_story("to see text content alongside tool blocks in the alpha view")
def test_text_and_tools_coexist(sculptor_instance_: SculptorInstance) -> None:
    """A multi_step with a text response and a write_file renders both text and chips."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "text", "args": {"text": "Creating the config file now."}},
    {"command": "write_file", "args": {"file_path": "config.json", "content": "{}"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Text content should be visible
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_contain_text("Creating the config file now.")

    # Chip row for the write should also be visible
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    expect(file_chip.first).to_contain_text("config.json")


@user_story("to see an error bash block and a chip row coexist in the same message")
def test_bash_with_error_and_write_coexist(sculptor_instance_: SculptorInstance) -> None:
    """An error bash block and a write chip row both render correctly."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "echo failure && exit 1"}},
    {"command": "write_file", "args": {"file_path": "ok.txt", "content": "recovery"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)

    # Bash block should be visible (error blocks stay collapsed)
    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()

    # Chip row for the write_file should also be visible
    chip_row = alpha_view.get_chip_rows()
    expect(chip_row).to_be_visible()

    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_contain_text("ok.txt")


@user_story("to see a chip row render for a simple single-file write")
def test_single_write_renders_chip_row(sculptor_instance_: SculptorInstance) -> None:
    """A standalone write_file renders a chip row with the correct filename."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "standalone_write.txt",
  "content": "standalone content"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)

    chip_rows = alpha_view.get_chip_rows()
    expect(chip_rows).to_have_count(1)

    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_contain_text("standalone_write.txt")
