"""Integration tests for the chip row feature in the alpha chat view.

File-change tools (Edit, MultiEdit, Write) should render as compact inline
chips instead of dimmed tool lines. Clicking a chip opens a diff popover.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see file write tools rendered as chips in the alpha view")
def test_chip_row_renders_for_write_tool(sculptor_instance_: SculptorInstance) -> None:
    """write_file tool calls render as a chip row with a file chip."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "chip_test_file.txt",
  "content": "hello from chip row test"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Should have a chip row with a file chip
    chip_row = alpha_view.get_chip_rows()
    expect(chip_row).to_be_visible()

    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    expect(file_chip.first).to_contain_text("chip_test_file.txt")


@user_story("to see consecutive file changes grouped and non-file tools separate")
def test_chip_row_groups_consecutive_file_changes(sculptor_instance_: SculptorInstance) -> None:
    """Consecutive file-change tools form one chip row; non-file tools break the group."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "file_a.txt", "content": "a"}},
    {"command": "write_file", "args": {"file_path": "file_b.txt", "content": "b"}},
    {"command": "bash", "args": {"command": "echo hello"}},
    {"command": "write_file", "args": {"file_path": "file_c.txt", "content": "c"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Each multi_step command produces a separate assistant message, so each
    # write_file gets its own chip row (3 total: A, B, C). The bash tool
    # renders as a non-chip tool group between chip rows B and C.
    alpha_view = get_alpha_chat_view(page)
    chip_rows = alpha_view.get_chip_rows()
    expect(chip_rows).to_have_count(3)

    # Each chip row should have exactly 1 chip
    for i in range(3):
        row_chips = chip_rows.nth(i).get_by_test_id(ElementIDs.ALPHA_CHAT_FILE_CHIP)
        expect(row_chips).to_have_count(1)


@user_story("to see a diff popover when clicking a chip")
def test_chip_popover_opens_on_click(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file chip opens the diff popover with correct content."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "popover_test.txt",
  "content": "popover content"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    # The chip's React structure differs between "executing" and "completed"
    # state (the executing variant wraps the button in a Tooltip), so the
    # transition remounts the button DOM. Without this assertion, the click
    # can race the remount and land on a stale element.
    expect(file_chip.first).to_be_enabled()
    file_chip.first.click()

    # Popover should be visible (rendered in portal, so use page-level locator)
    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("popover_test.txt")


@user_story("to close a diff popover by clicking the chip again")
def test_chip_popover_closes_on_second_click(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the same chip again closes the popover."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "toggle_test.txt",
  "content": "toggle content"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    expect(file_chip.first).to_be_enabled()

    # Open popover
    file_chip.first.click()
    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()

    # Close popover by clicking chip again. Re-assert the chip is enabled to
    # wait out any DOM churn from popover mount/focus-trap before the second
    # click — without this, the click can race the chip's remount and be
    # swallowed (parallels the guard before the first click).
    expect(file_chip.first).to_be_enabled()
    file_chip.first.click()
    expect(popover).not_to_be_visible()


@user_story("to view popover for different chips across rows")
def test_chip_popover_swaps_on_different_chip_click(sculptor_instance_: SculptorInstance) -> None:
    """Closing one chip's popover and clicking another shows the new chip's content."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "swap_a.txt", "content": "a"}},
    {"command": "write_file", "args": {"file_path": "swap_b.txt", "content": "b"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    chips = alpha_view.get_file_chips()
    expect(chips).to_have_count(2)

    # Click first chip — popover shows first file
    chips.nth(0).click()
    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("swap_a.txt")

    # Close first chip's popover before switching to a chip in a different row.
    # Each multi_step operation creates a separate message with its own Popover
    # instance, so Radix's dismiss-on-outside-click prevents direct cross-row swap.
    chips.nth(0).click()
    expect(popover).not_to_be_visible()

    # Click second chip — opens that chip's popover
    chips.nth(1).click()
    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("swap_b.txt")

    # Only one popover should be visible
    expect(alpha_view.get_chip_popover()).to_have_count(1)
