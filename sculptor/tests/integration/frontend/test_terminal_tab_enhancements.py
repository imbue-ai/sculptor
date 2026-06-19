"""Integration tests for terminal tab enhancements.

Tests cover:
- Terminal tab inline rename via double-click
- Terminal context menu has Rename and Close others items
- Terminal tabs use compact variant (tabs above content, no heading)
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.terminal import get_add_terminal_button
from sculptor.testing.elements.terminal import get_inline_rename_input
from sculptor.testing.elements.terminal import get_tab_context_menu_close_others
from sculptor.testing.elements.terminal import get_tab_context_menu_rename
from sculptor.testing.elements.terminal import get_terminal_heading
from sculptor.testing.elements.terminal import get_terminal_tabs
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.mark.isolated
@user_story("to rename a terminal tab via double-click")
def test_terminal_tab_double_click_rename(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Double-clicking a terminal tab opens inline rename, Enter commits the new name.

    Steps:
    1. Create a workspace and open the terminal
    2. Double-click the terminal tab
    3. Verify the inline rename input appears
    4. Type a new name and press Enter
    5. Verify the terminal tab shows the new name
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Terminal test", workspace_name="Term WS")
    open_terminal_and_wait(page)

    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(1)
    terminal_tabs.first.dblclick()

    rename_input = get_inline_rename_input(page)
    expect(rename_input).to_be_visible()

    rename_input.fill("My Shell")
    rename_input.press("Enter")
    expect(rename_input).not_to_be_visible()

    expect(terminal_tabs.first).to_have_text("My Shell")


@user_story("to see Rename and Close others items in terminal context menu")
def test_terminal_context_menu_has_close_all_and_rename(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking a terminal tab shows Rename and Close others items.

    Steps:
    1. Create workspace, open terminal, add a second tab
    2. Right-click a terminal tab
    3. Verify Rename and Close others items are visible
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Term menu test", workspace_name="Term Menu WS")
    open_terminal_and_wait(page)

    add_terminal_button = get_add_terminal_button(page)
    add_terminal_button.click()

    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(2)

    terminal_tabs.nth(0).click(button="right")

    rename_item = get_tab_context_menu_rename(page)
    expect(rename_item).to_be_visible()

    close_others_item = get_tab_context_menu_close_others(page)
    expect(close_others_item).to_be_visible()


@user_story("to see terminal tabs above content with no heading")
def test_terminal_compact_layout_no_heading(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Terminal panel uses compact tab variant: heading removed, tabs above content.

    Steps:
    1. Create workspace and open terminal
    2. Verify the terminal heading is not visible
    3. Verify terminal tabs are rendered
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Layout test", workspace_name="Layout WS")
    open_terminal_and_wait(page)

    terminal_heading = get_terminal_heading(page)
    expect(terminal_heading).to_have_count(0)

    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(1)
