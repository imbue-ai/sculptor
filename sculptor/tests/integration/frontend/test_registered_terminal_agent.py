"""Integration test for registered terminal agents launching their program.

A fake registered program (an inline shell snippet that drives the REAL
`sculpt signal` CLI) is registered via TOML; creating the agent must run it
as a shell job in the agent's terminal (REQ-REG-2): the launch command is
written exactly once after the shell's first output, its signals drive the
tab dot, and quitting it lands at a usable shell prompt with no relaunch
(REQ-LIFE-5).
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import run_command_in_agent_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Banner → busy → (long enough for the dot assertion) → idle → wait for one
# line of stdin → exit marker. Runs as a job of the login shell.
_FAKE_TUI_COMMAND = (
    "echo FAKE-TUI-BANNER; sculpt signal busy; sleep 8; sculpt signal idle; read -r _line; echo fake-tui-exited"
)


@user_story("to have a registered terminal agent launch its program in the terminal")
def test_registered_terminal_agent_launches_program(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Registered Launch WS")
    agent_tab_bar = PlaywrightAgentTabBarElement(page)

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-tui.toml").write_text(
        f'display_name = "Fake TUI"\nlaunch_command = "{_FAKE_TUI_COMMAND}"\n'
    )
    try:
        agent_tab_bar.open_agent_type_menu()
        registered_item = agent_tab_bar.get_agent_type_menu_item_registered("fake-tui")
        expect(registered_item).to_be_visible()
        registered_item.click()

        terminal_tab = agent_tab_bar.get_agent_tab_by_name("Fake TUI 1").first
        expect(terminal_tab).to_be_visible()
        expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_be_visible()
        expect(get_agent_terminal_textarea(page)).to_be_attached()

        # The launch command ran (the readiness wait didn't swallow it).
        wait_for_xterm_substring(page, "FAKE-TUI-BANNER")

        # The program's own signals drive the dot: busy → spinner, idle → neutral.
        expect(terminal_tab).to_have_attribute("data-dot-status", "running", timeout=15_000)
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"), timeout=20_000)

        # Quit the program (it reads one line of stdin) — this lands at a
        # usable shell prompt in the same terminal, with no relaunch.
        run_command_in_agent_terminal(page, "q")
        wait_for_xterm_substring(page, "fake-tui-exited")
        run_command_in_agent_terminal(page, "echo back-at-shell")
        wait_for_xterm_substring(page, "back-at-shell")

        # Still neutral after the program exited.
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))
    finally:
        (registrations_dir / "fake-tui.toml").unlink(missing_ok=True)
