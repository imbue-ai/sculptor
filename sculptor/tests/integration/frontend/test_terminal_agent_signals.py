"""Integration tests for terminal-agent signals driving the tab status dot.

Signals are posted from inside the agent's own terminal via the `sculpt
signal` CLI (REQ-SIG-3), which reads SCULPT_AGENT_ID / SCULPT_API_PORT from
the injected shell env and posts to the local HTTP event API (REQ-SIG-1/5).
busy → spinner, waiting → attention dot, idle → calm neutral; files-changed
refreshes the Changes panel (REQ-SIG-6).
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.file_tree import get_changes_tree
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import run_command_in_agent_terminal
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _post_signal_from_terminal(page: Page, subcommand: str) -> None:
    """Run `sculpt signal <subcommand>` inside the agent's shell.

    The CLI resolves the agent and port from the injected env and
    self-fetches the session token — exactly how real hooks invoke it.
    """
    run_command_in_agent_terminal(page, f"sculpt signal {subcommand}")


@user_story("to see a terminal agent's tab reflect the signals its program posts")
def test_terminal_agent_signals_drive_tab_status_dot(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Signals WS")
    agent_tab_bar = PlaywrightAgentTabBarElement(page)

    agent_tab_bar.open_agent_type_menu()
    agent_tab_bar.get_agent_type_menu_item_terminal().click()
    terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
    expect(terminal_tab).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_be_visible()
    expect(get_agent_terminal_textarea(page)).to_be_attached()
    page.wait_for_timeout(3_000)

    # No signals yet: calm neutral (read/unread), never running/waiting.
    expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))

    _post_signal_from_terminal(page, "busy")
    expect(terminal_tab).to_have_attribute("data-dot-status", "running", timeout=15_000)

    _post_signal_from_terminal(page, "waiting")
    expect(terminal_tab).to_have_attribute("data-dot-status", "waiting", timeout=15_000)

    _post_signal_from_terminal(page, "idle")
    expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"), timeout=15_000)

    # files-changed refreshes the Changes panel for a file the shell created.
    run_command_in_agent_terminal(page, "touch signal_file.txt")
    _post_signal_from_terminal(page, "files-changed")
    task_page.activate_changes_panel()
    changes_tree = get_changes_tree(page)
    expect(changes_tree).to_be_visible()
    expect(changes_tree.get_tree_rows().filter(has_text="signal_file.txt")).to_be_visible(timeout=15_000)
