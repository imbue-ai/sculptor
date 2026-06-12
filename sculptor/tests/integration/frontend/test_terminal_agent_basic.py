"""Integration tests for plain Terminal agents (terminal-agents phase 1).

A Terminal agent's main panel is a PTY terminal instead of a chat
(REQ-UI-1/2), the shell runs in the workspace code directory (REQ-TERM-1),
file changes made in the shell reach the Changes panel via the periodic
diff refresh (REQ-TERM-3), the PTY survives tab switches (REQ-LIFE-1), and
the tab behaves like any other agent tab (REQ-UI-3, REQ-TERM-2).
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.file_tree import get_changes_tree
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import run_command_in_agent_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_terminal_agent(agent_tab_bar: PlaywrightAgentTabBarElement) -> None:
    agent_tab_bar.open_agent_type_menu()
    agent_tab_bar.get_agent_type_menu_item_terminal().click()


def _wait_for_terminal_ready(page: Page) -> None:
    """Wait until the agent terminal's xterm is mounted and the shell is up.

    The backend PTY may still be spawning when the panel mounts (the
    WebSocket retries 4404 closes every 2s), so give the prompt a moment
    after the textarea attaches.
    """
    expect(get_agent_terminal_textarea(page)).to_be_attached()
    page.wait_for_timeout(3_000)


@user_story("to use a plain terminal agent alongside chat agents")
def test_terminal_agent_basic(sculptor_instance_: SculptorInstance) -> None:
    """Create a Terminal agent, use the shell, see diffs refresh, switch tabs."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Agent WS")
    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    _create_terminal_agent(agent_tab_bar)
    expect(agent_tabs).to_have_count(2)
    terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
    expect(terminal_tab).to_be_visible()

    # The terminal occupies the chat space: panel present, chat input absent.
    expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_have_count(0)

    # Shell round trip in the workspace code directory.
    _wait_for_terminal_ready(page)
    run_command_in_agent_terminal(page, "echo hello-sculptor")
    wait_for_xterm_substring(page, "hello-sculptor")

    # A file created in the shell reaches the Changes panel via the periodic
    # diff refresh — Sculptor cannot see the shell's commands, only git state.
    run_command_in_agent_terminal(page, "touch a_new_file.txt")
    task_page.activate_changes_panel()
    changes_tree = get_changes_tree(page)
    expect(changes_tree).to_be_visible()
    expect(changes_tree.get_tree_rows().filter(has_text="a_new_file.txt")).to_be_visible(timeout=15_000)

    # While idle the tab's status dot is neutral (read/unread) — terminal
    # agents never derive running/waiting from chat state (REQ-TERM-2).
    expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))

    # Tab switching: the Claude tab still has its chat; switching back to the
    # terminal reconnects with the scrollback replay (the PTY survived the
    # WebSocket disconnect — REQ-LIFE-1).
    agent_tabs.first.click()
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_have_count(0)
    terminal_tab.click()
    expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_be_visible()
    wait_for_xterm_substring(page, "hello-sculptor")


@user_story("to manage terminal agent tabs like any other agent tab")
def test_terminal_agent_tab_rename_and_delete(sculptor_instance_: SculptorInstance) -> None:
    """Terminal agent tabs rename and delete exactly like chat-agent tabs (REQ-UI-3)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Tab WS")
    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tabs = agent_tab_bar.get_agent_tabs()

    _create_terminal_agent(agent_tab_bar)
    expect(agent_tabs).to_have_count(2)
    terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
    expect(terminal_tab).to_be_visible()

    # Rename via the context menu.
    agent_tab_bar.open_context_menu(terminal_tab)
    agent_tab_bar.get_context_menu_rename_item().click()
    rename_input = agent_tab_bar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    expect(rename_input).to_be_focused()
    rename_input.fill("My Terminal")
    rename_input.press("Enter")
    expect(rename_input).not_to_be_visible()
    expect(agent_tab_bar.get_agent_tab_by_name("My Terminal")).to_have_count(1)

    # Delete via the context menu, with the standard confirmation.
    agent_tab_bar.open_context_menu(agent_tab_bar.get_agent_tab_by_name("My Terminal").first)
    agent_tab_bar.get_context_menu_delete_item().click()
    confirm_button = agent_tab_bar.get_delete_confirmation_confirm_button()
    expect(confirm_button).to_be_visible()
    confirm_button.click()
    expect(agent_tabs).to_have_count(1)
