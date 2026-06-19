"""Integration tests for context menus on terminal tab bars.

Tests cover:
- Closing other terminal tabs via the terminal tab context menu
"""

from playwright.sync_api import expect

from sculptor.testing.elements.terminal import get_add_terminal_button
from sculptor.testing.elements.terminal import get_tab_context_menu_close_others
from sculptor.testing.elements.terminal import get_terminal_tabs
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to close other terminal tabs via the context menu")
def test_terminal_tab_context_menu_close_others(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a terminal tab and selecting Close Others removes all other tabs.

    Creates a workspace, opens the terminal panel, adds two additional terminal tabs
    (3 total), right-clicks the second terminal tab, selects Close Others, and
    verifies only 1 tab remains.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Terminal test", workspace_name="Terminal WS")

    # Open the terminal panel (it is not visible by default)
    open_terminal_and_wait(page)

    # Add two additional terminal tabs (3 total)
    add_terminal_button = get_add_terminal_button(page)
    add_terminal_button.click()
    add_terminal_button.click()

    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(3)

    # Right-click the second terminal tab to open the context menu
    terminal_tabs.nth(1).click(button="right")

    # Click "Close others" from the context menu
    close_others_item = get_tab_context_menu_close_others(page)
    expect(close_others_item).to_be_visible()
    close_others_item.click()

    expect(terminal_tabs).to_have_count(1)
