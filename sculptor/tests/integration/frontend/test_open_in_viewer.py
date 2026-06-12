"""Integration tests for opening a file in the diff viewer from the chat panel.

Tests verify that opening a file diff tool result from the chat opens the
diff panel with actual file content (not "Could not load file content").
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_panel import PlaywrightDiffPanelElement
from sculptor.testing.elements.diff_panel import get_diff_panel_from_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ========== Constants ==========

WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "greeting.txt",
  "content": "Hello, world!\\nThis is a new file.\\n"
}`"""

EDIT_FILE_PROMPT = """\
fake_claude:edit_file `{
  "file_path": "greeting.txt",
  "old_string": "Hello, world!",
  "new_string": "Hi, everyone!"
}`"""


# ========== Helper Functions ==========


def open_diff_via_alpha_chip(chat_panel: PlaywrightChatPanelElement, file_path: str) -> None:
    """Click the most-recent alpha file chip for `file_path` and open its full diff."""
    file_chip = chat_panel.get_file_chips().filter(has_text=file_path)
    expect(file_chip.last).to_be_visible()
    file_chip.last.click()

    popover = chat_panel.get_chip_popover()
    expect(popover).to_be_visible()
    chat_panel.get_chip_view_full_diff_button().click()


def assert_diff_panel_shows_content(diff_panel: PlaywrightDiffPanelElement, tab_text: str) -> None:
    """Assert the diff panel is open with a tab and shows content (not an error)."""
    expect(diff_panel).to_be_visible()

    tab = diff_panel.get_tab_by_name(tab_text)
    expect(tab.first).to_be_visible()

    expect(diff_panel).not_to_contain_text("Could not load file content")


def assert_diff_panel_shows_diff_view(diff_panel: PlaywrightDiffPanelElement, tab_text: str) -> None:
    """Assert the diff panel shows an actual diff view (not a read-only file preview)."""
    expect(diff_panel).to_be_visible()

    tab = diff_panel.get_tab_by_name(tab_text)
    expect(tab.first).to_be_visible()

    unified = diff_panel.get_unified_diff_views()
    split = diff_panel.get_split_view()
    expect(unified.or_(split)).to_be_visible(timeout=30_000)

    expect(diff_panel.get_read_only_preview()).to_have_count(0)


# ========== Tests ==========


@user_story("to open a created repo file in the diff viewer from the chat panel")
def test_open_created_file_in_diff_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Test that clicking 'Open in viewer' on a Write tool result opens the
    diff panel with the file's content visible (not 'Could not load file content').
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_FILE_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the file's full diff via the alpha file chip
    open_diff_via_alpha_chip(chat_panel, "greeting.txt")

    # Verify the diff panel shows file content
    diff_panel = get_diff_panel_from_page(page)
    assert_diff_panel_shows_content(diff_panel, "greeting.txt")


# SCU-366 outside-workspace routing is covered by the Vitest unit test in
# chat-alpha/__tests__/AlphaChipDiffPopover.test.tsx — the integration flow
# (file chip → popover) doesn't reliably open in headless Playwright for
# outside-workspace paths.


@user_story("to open an edited repo file in the diff viewer from the chat panel")
def test_open_edited_file_in_diff_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Test that clicking 'Open in viewer' on an Edit tool result opens the
    diff panel with an actual diff view showing the changes (not a read-only
    full-file preview).
    """
    page = sculptor_instance_.page

    # Step 1: Create the file
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_FILE_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Step 2: Edit the file in a follow-up turn
    send_chat_message(chat_panel=chat_panel, message=EDIT_FILE_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Step 3: Open the edited file's full diff via the alpha file chip
    open_diff_via_alpha_chip(chat_panel, "greeting.txt")

    # Step 4: Verify the diff panel shows an actual diff view, not a read-only preview
    diff_panel = get_diff_panel_from_page(page)
    assert_diff_panel_shows_diff_view(diff_panel, "greeting.txt")
