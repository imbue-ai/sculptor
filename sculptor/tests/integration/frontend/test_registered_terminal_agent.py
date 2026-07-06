"""Integration tests for terminal agents' launch and restart behaviour.

A fake registered program (an inline shell snippet that drives the REAL
`sculpt signal` CLI) is registered via TOML; creating the agent must run it
as a shell job in the agent's terminal: the launch command is written
exactly once after the shell's first output, its signals drive the tab dot,
and quitting it lands at a usable shell prompt with no relaunch. Registered
agents resume their session across a backend restart, while a PLAIN terminal
agent relaunches as a bare fresh shell.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import get_xterm_buffer_text
from sculptor.testing.elements.terminal import run_command_in_agent_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_buffer_nonempty
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# Banner → busy → block on stdin (the busy state is sticky, held open until
# the test releases it) → idle → block on stdin again → exit marker. Runs as a
# job of the login shell. Gating busy→idle on a typed line instead of a
# wall-clock `sleep` keeps the transient running-dot assertion from racing CI
# latency.
_FAKE_TUI_COMMAND = (
    "echo FAKE-TUI-BANNER; sculpt signal busy; read -r _line; sculpt signal idle; read -r _line; echo fake-tui-exited"
)


@user_story("to have a registered terminal agent launch its program in the terminal")
def test_registered_terminal_agent_launches_program(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Registered Launch WS")
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-tui.toml").write_text(
        f'display_name = "Fake TUI"\nlaunch_command = "{_FAKE_TUI_COMMAND}"\n'
    )
    try:
        dropdown.open()
        dropdown.open_agent_type_submenu()
        registered_item = dropdown.get_agent_type_item_registered("fake-tui")
        expect(registered_item).to_be_visible()
        registered_item.click()

        terminal_tab = panel_tabs.get_panel_tab_by_name("Fake TUI 1").first
        expect(terminal_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        expect(get_agent_terminal_textarea(page)).to_be_attached()

        # The launch command ran (the readiness wait didn't swallow it).
        wait_for_xterm_substring(page, "FAKE-TUI-BANNER")

        # The program's own signals drive the dot. busy is sticky and held open
        # until we release it, so the spinner is observable regardless of
        # machine speed.
        expect(terminal_tab).to_have_attribute("data-dot-status", "running")

        # Release the busy hold (first stdin line) → the program signals idle.
        run_command_in_agent_terminal(page, "release")
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))

        # Quit the program (it reads a second line of stdin) — this lands at a
        # usable shell prompt in the same terminal, with no relaunch.
        run_command_in_agent_terminal(page, "q")
        wait_for_xterm_substring(page, "fake-tui-exited")
        run_command_in_agent_terminal(page, "echo back-at-shell")
        wait_for_xterm_substring(page, "back-at-shell")

        # Still neutral after the program exited.
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))
    finally:
        (registrations_dir / "fake-tui.toml").unlink(missing_ok=True)


# The session id must be durably persisted before the first instance is torn
# down, or the restart relaunches instead of resuming. `until sculpt signal ...`
# retries until the report succeeds (CLI exit 0 == the backend committed the id);
# a plain `; sculpt signal ... ;` would let SESSION-REPORTED print even when the
# report fails transiently under load, tearing the instance down unpersisted.
# SESSION-REPORTED is printf-assembled so it appears only in the program output,
# never the echoed command line -- the xterm wait must trip on the output.
_FAKE_RESUME_LAUNCH = (
    "echo FIRST-RUN-BANNER; until sculpt signal session-id fake-session-42; do sleep 0.2; done; "
    + "printf %sREPORTED SESSION-; echo; read -r _line"
)
_FAKE_RESUME_TEMPLATE = "echo RESUMED-WITH {session_id}; read -r _line"


@user_story("to have a registered agent resume its session after a backend restart")
def test_registered_terminal_agent_resumes_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """After a restart the handler relaunches via the rendered resume command
    — the reported session id flows TOML → signal → state → resume template."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Resume WS")
        dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

        registrations_dir = instance.sculptor_folder / "terminal_agents"
        registrations_dir.mkdir(parents=True, exist_ok=True)
        (registrations_dir / "fake-resume.toml").write_text(
            f'display_name = "Fake Resume"\n'
            f'launch_command = "{_FAKE_RESUME_LAUNCH}"\n'
            f'resume_command_template = "{_FAKE_RESUME_TEMPLATE}"\n'
        )

        dropdown.open()
        dropdown.open_agent_type_submenu()
        registered_item = dropdown.get_agent_type_item_registered("fake-resume")
        expect(registered_item).to_be_visible()
        registered_item.click()
        expect(get_agent_terminal_panel(page)).to_be_visible()

        wait_for_xterm_substring(page, "FIRST-RUN-BANNER")
        # The session id reached the backend (the sculpt call returned).
        wait_for_xterm_substring(page, "SESSION-REPORTED")

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        navigate_to_workspace(page)

        panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
        resume_tab = panel_tabs.get_panel_tab_by_name("Fake Resume 1").first
        expect(resume_tab).to_be_visible()
        resume_tab.click()
        expect(get_agent_terminal_panel(page)).to_be_visible()

        # The relaunch used the rendered resume command with the quoted id.
        wait_for_xterm_substring(page, "RESUMED-WITH fake-session-42")


@user_story("to get a fresh shell in a plain terminal agent after a restart")
def test_plain_terminal_agent_gets_fresh_shell_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Plain terminals relaunch as a bare fresh shell after a backend restart —
    no command replayed, pre-restart scrollback gone (expected per spec)."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        # A terminal FIRST agent: the new-workspace form's agent-type select still
        # offers bare Terminal (the panel-tab add-dropdown does not).
        start_task_and_wait_for_ready(page, workspace_name="Fresh Shell WS", agent_type="terminal")
        expect(get_agent_terminal_panel(page)).to_be_visible()
        expect(get_agent_terminal_textarea(page)).to_be_attached()
        wait_for_xterm_buffer_nonempty(page)
        run_command_in_agent_terminal(page, "echo marker-before-restart")
        wait_for_xterm_substring(page, "marker-before-restart")

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        navigate_to_workspace(page)

        # The terminal is the workspace's only agent; activate its tab.
        panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
        terminal_tab = panel_tabs.get_panel_tabs().first
        expect(terminal_tab).to_be_visible()
        terminal_tab.click()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        expect(get_agent_terminal_textarea(page)).to_be_attached()
        wait_for_xterm_buffer_nonempty(page)

        # Fresh, usable shell; pre-restart scrollback is gone.
        run_command_in_agent_terminal(page, "echo fresh-shell-marker")
        wait_for_xterm_substring(page, "fresh-shell-marker")
        assert "marker-before-restart" not in get_xterm_buffer_text(page), (
            "Expected the plain terminal to relaunch as a fresh shell, but pre-restart scrollback was replayed"
        )
