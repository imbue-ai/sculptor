"""Integration tests for terminal-agent signals driving the tab status dot.

Signals are posted from inside a registered terminal agent's own shell via the
`sculpt signal` CLI, which reads SCULPT_AGENT_ID / SCULPT_API_PORT from the
injected shell env and posts to the local HTTP event API. busy → spinner,
waiting → attention dot, idle → calm neutral; files-changed refreshes the
Changes panel.

The bare "terminal" agent type was removed from the product; this exercises the
same signal→dot mechanism on a registered terminal agent — the model the bundled
Claude CLI agent uses — by registering a `.toml` whose launch command drops to a
usable shell prompt so the test can drive `sculpt signal` directly.
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.file_tree import get_changes_tree
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import run_command_in_agent_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A registered agent whose launch command just announces readiness and then
# falls through to the login shell prompt, so the test drives `sculpt signal`
# by typing into the terminal exactly as a real program's hooks would.
_SIGNAL_AGENT_LAUNCH = "echo SIGNAL-AGENT-READY"


def _post_signal_from_terminal(page: Page, subcommand: str) -> None:
    """Run `sculpt signal <subcommand>` inside the agent's shell.

    The CLI resolves the agent and port from the injected env and
    self-fetches the session token — exactly how real hooks invoke it.
    """
    run_command_in_agent_terminal(page, f"sculpt signal {subcommand}")


@user_story("to see a registered terminal agent's tab reflect the signals its program posts")
def test_terminal_agent_signals_drive_tab_status_dot(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Signals WS")
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "signal-agent.toml").write_text(
        f'display_name = "Signal Agent"\nlaunch_command = "{_SIGNAL_AGENT_LAUNCH}"\n'
    )
    try:
        dropdown.open()
        dropdown.open_agent_type_submenu()
        dropdown.get_agent_type_item_registered("signal-agent").click()
        terminal_tab = panel_tabs.get_panel_tab_by_name("Signal Agent 1").first
        expect(terminal_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        expect(get_agent_terminal_textarea(page)).to_be_attached()
        # The launch command ran and dropped to a usable shell prompt.
        wait_for_xterm_substring(page, "SIGNAL-AGENT-READY")

        # No signals yet: calm neutral (read/unread), never running/waiting.
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))

        _post_signal_from_terminal(page, "busy")
        expect(terminal_tab).to_have_attribute("data-dot-status", "running")

        _post_signal_from_terminal(page, "waiting")
        expect(terminal_tab).to_have_attribute("data-dot-status", "waiting")

        _post_signal_from_terminal(page, "idle")
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))

        # files-changed refreshes the Changes panel for a file the shell created.
        run_command_in_agent_terminal(page, "touch signal_file.txt")
        _post_signal_from_terminal(page, "files-changed")
        task_page.activate_changes_panel()
        changes_tree = get_changes_tree(page)
        expect(changes_tree).to_be_visible()
        expect(changes_tree.get_tree_rows().filter(has_text="signal_file.txt")).to_be_visible()
    finally:
        (registrations_dir / "signal-agent.toml").unlink(missing_ok=True)
