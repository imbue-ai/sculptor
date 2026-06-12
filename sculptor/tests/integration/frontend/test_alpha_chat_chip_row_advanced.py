"""Advanced integration tests for the chip row feature in the alpha chat view.

Covers edit-tool rendering, keyboard interactions, nested paths, mixed tool
sequences, popover diff content, and many-file chip rows.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see edit tool calls rendered as chips in the alpha view")
def test_chip_row_renders_for_edit_tool(sculptor_instance_: SculptorInstance) -> None:
    """edit_file tool calls render as a chip row with a file chip."""
    page = sculptor_instance_.page

    # First create the file so the edit has something to work with
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "edit_target.txt", "content": "original"}},
    {"command": "edit_file", "args": {"file_path": "edit_target.txt", "old_string": "original", "new_string": "modified"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Write + edit on the same file are merged into a single chip
    file_chips = alpha_view.get_file_chips()
    expect(file_chips).to_have_count(1)

    # The chip should reference the edited file
    expect(file_chips.first).to_contain_text("edit_target.txt")


@user_story("to preview the diff by hovering over a file chip")
def test_chip_row_hover_opens_popover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Hovering over a file chip should open the diff popover after the hover-delay window."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "hover_test.txt",
  "content": "hover content"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()

    # Hover (no click) — the usePillHoverDelay machine opens the popover
    # after ~600ms. Playwright's expect retries until visible.
    file_chip.first.hover()
    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()


@user_story("to close a diff popover by pressing Escape")
def test_chip_row_keyboard_escape_closes_popover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Escape while a popover is open should close it."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "escape_test.txt",
  "content": "escape content"
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

    # Press Escape to close the popover
    page.keyboard.press("Escape")
    expect(popover).not_to_be_visible()


@user_story("to see only the filename in the chip for deeply nested paths")
def test_chip_shows_filename_for_nested_path(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A file at a nested path should display only the filename in its chip."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "src/components/Button.tsx",
  "content": "export const Button = () => <button>Click</button>;"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    expect(file_chip.first).to_contain_text("Button.tsx")


@user_story("to see chips after editing a previously written file")
def test_chip_row_edit_after_write_same_file(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Writing then editing the same file merges into a single chip."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "write_edit.txt", "content": "first version"}},
    {"command": "edit_file", "args": {"file_path": "write_edit.txt", "old_string": "first version", "new_string": "second version"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Write + edit on the same file are merged into a single chip
    alpha_view = get_alpha_chat_view(page)
    file_chips = alpha_view.get_file_chips()
    expect(file_chips).to_have_count(1)
    expect(file_chips.first).to_contain_text("write_edit.txt")


@user_story("to see separate chip rows when a bash tool appears between file tools")
def test_multiple_chip_rows_in_message(sculptor_instance_: SculptorInstance) -> None:
    """File write, bash, then file write should create 2 chip rows separated by a bash block."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "before_bash.txt", "content": "before"}},
    {"command": "bash", "args": {"command": "echo separator"}},
    {"command": "write_file", "args": {"file_path": "after_bash.txt", "content": "after"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Should have 2 separate chip rows
    alpha_view = get_alpha_chat_view(page)
    chip_rows = alpha_view.get_chip_rows()
    expect(chip_rows).to_have_count(2)

    # A bash block should exist between them
    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block).to_be_visible()


@user_story("to see diff content inside a chip popover")
def test_chip_popover_shows_diff_content(sculptor_instance_: SculptorInstance) -> None:
    """Opening a chip popover should show the file content or diff."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "diff_content_test.txt",
  "content": "line one\\nline two\\nline three"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    expect(file_chip.first).to_be_enabled()
    file_chip.first.click()

    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()

    # Popover should contain at minimum the filename
    expect(popover).to_contain_text("diff_content_test.txt")


@user_story("to see all chips when many files are written at once")
def test_chip_row_with_many_files(sculptor_instance_: SculptorInstance) -> None:
    """Writing 5 different files should produce 5 chips."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "many_a.txt", "content": "a"}},
    {"command": "write_file", "args": {"file_path": "many_b.txt", "content": "b"}},
    {"command": "write_file", "args": {"file_path": "many_c.txt", "content": "c"}},
    {"command": "write_file", "args": {"file_path": "many_d.txt", "content": "d"}},
    {"command": "write_file", "args": {"file_path": "many_e.txt", "content": "e"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # All 5 files should appear as chips
    alpha_view = get_alpha_chat_view(page)
    file_chips = alpha_view.get_file_chips()
    expect(file_chips).to_have_count(5, timeout=30_000)

    # Verify each file is represented
    expected_files = ["many_a.txt", "many_b.txt", "many_c.txt", "many_d.txt", "many_e.txt"]
    for i, filename in enumerate(expected_files):
        expect(file_chips.nth(i)).to_contain_text(filename)


@user_story("to open a full diff from a chip popover that reflects the current uncommitted state")
def test_view_full_diff_for_multi_edit_file_shows_correct_line_count(
    sculptor_instance_: SculptorInstance,
) -> None:
    """'View full diff' for a multi-written file must show the workspace uncommitted diff.

    When a file is written twice in the same assistant message (via
    ``parallel_tools``), both writes produce ``DiffToolContent`` with separate
    ``diff --git`` headers.  Before the fix, ``AlphaChipDiffPopover`` joined
    them with ``\\n`` and stored the multi-file diff string in the persisted diff
    tab.  Pierre's ``FileDiff`` then threw "Provided patch must contain exactly
    1 file diff", crashing the workspace UI.

    After the fix, no ``diffString`` is embedded in the tab; the diff panel
    looks up the current uncommitted diff for the file, which correctly shows
    only the final state.
    """
    page = sculptor_instance_.page

    # Use parallel_tools so both writes are in ONE assistant message.
    # This makes them land in the same chip segment and merge into one chip.
    # Both Write tool results get synthetic DiffToolContent (each with its own
    # "diff --git" header), which is the condition that triggers the crash.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:parallel_tools `{
  "tools": [
    {"tool_name": "Write", "tool_input": {"file_path": "multi_write.txt", "content": "version one"}},
    {"tool_name": "Write", "tool_input": {"file_path": "multi_write.txt", "content": "version two\\nextra line"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Both writes target multi_write.txt so they merge into one chip.
    alpha_view = get_alpha_chat_view(page)
    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()
    expect(file_chip.first).to_be_enabled()
    file_chip.first.click()

    popover = alpha_view.get_chip_popover()
    expect(popover).to_be_visible()

    # Click "View full diff" to open the diff panel.
    view_full_diff_btn = alpha_view.get_chip_view_full_diff_btn()
    expect(view_full_diff_btn).to_be_visible()
    view_full_diff_btn.click()

    # The diff panel must open (before the fix, Pierre crashes here because
    # the joined diff string has two "diff --git" headers).
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_be_visible()
    expect(diff_header).to_contain_text("multi_write")

    # The diff header must show the workspace uncommitted diff (+2 for the
    # final 2-line file), NOT the chip's summed tool-result stats (+3).
    # Before the fix, the joined multi-file diffString either crashes Pierre
    # or shows inflated line counts.
    expect(diff_header).to_contain_text("+2")
