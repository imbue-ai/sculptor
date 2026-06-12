"""Regression test: Copy File Path should copy the workspace code path, not the source repo path.

Bug: In clone-mode workspaces, clicking "Copy file path" from the three-dots menu on a
diff file header copies the path rooted at the user's source repository instead of the
workspace's clone directory.

For example, it copies:
  /Users/user/work/sculptor/src/app.py
instead of:
  /Users/user/.sculptor_data/workspaces/<id>/code/src/app.py

Root cause: handleCopyFilePath in useFileMenuGroups.tsx always uses repoInfo.repoPath
(the source repo) to construct the absolute path, ignoring the workspace's clone directory.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.diff_panel import get_diff_panel_from_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "src/new_file.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to copy a file's absolute path and get the workspace clone path")
def test_copy_file_path_uses_workspace_code_path(sculptor_instance_: SculptorInstance) -> None:
    """Copy file path in a clone-mode workspace should use the workspace's code directory.

    Steps:
    1. Create a workspace (clone mode, the default) with a FakeClaude write_file command
    2. Open the diff view via the alpha file chip's "View full diff" action
    3. Install a clipboard interceptor
    4. Click the three-dots menu on the diff file header
    5. Click "Copy file path"
    6. Assert the clipboard path lives under the sculptor data folder (workspace clone)
    7. Assert the clipboard path ends with /code/<relative_file_path>
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    diff_panel = get_diff_panel_from_page(page)

    # Open the diff via the alpha file chip → chip popover → "View full diff".
    file_chip = chat_panel.get_file_chips().filter(has_text="new_file.py")
    expect(file_chip.first).to_be_visible()
    file_chip.first.click()

    popover = chat_panel.get_chip_popover()
    expect(popover).to_be_visible()
    chat_panel.get_chip_view_full_diff_button().click()

    # The diff panel should open with a file header showing the file path.
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_be_visible()

    # Install a clipboard interceptor so we can read what was written.
    install_clipboard_interceptor(page)

    # Click the "..." dropdown button in the diff header to open the file menu.
    menu_trigger = diff_panel.get_file_header_menu_trigger()
    menu_trigger.click()

    # Click "Copy file path" from the dropdown menu.
    copy_path_item = diff_panel.get_copy_file_path_menu_item()
    expect(copy_path_item).to_be_visible()
    copy_path_item.click()

    # Verify the clipboard contains the correct workspace path, not the source repo path.
    clipboard_value = read_intercepted_clipboard(page)
    assert clipboard_value is not None, "Clipboard should contain a value after clicking Copy file path"

    # Resolve symlinks on the clipboard value too (macOS: /var -> /private/var).
    resolved_clipboard = str(Path(clipboard_value).resolve())
    sculptor_folder = str(sculptor_instance_.sculptor_folder.resolve())

    # The path must live under the sculptor data folder (the workspace clone), not the source repo.
    assert resolved_clipboard.startswith(sculptor_folder), (
        f"Expected clipboard to start with sculptor folder '{sculptor_folder}', got '{resolved_clipboard}'"
    )
    assert resolved_clipboard.endswith("/code/src/new_file.py"), (
        f"Expected clipboard to end with '/code/src/new_file.py', got '{resolved_clipboard}'"
    )
