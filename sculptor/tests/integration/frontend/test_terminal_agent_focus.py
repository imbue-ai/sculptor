"""Regression test: switching to a terminal agent's panel tab must focus its pane.

A terminal agent's main panel is a PTY terminal that occupies the chat space.
The terminal is the agent's only input surface, so selecting its panel tab
should place keyboard focus into the terminal immediately — the user must be
able to type without first clicking into the pane (SCU-1578).

Terminal-running agents are created from registered terminal programs via the
section `+` dropdown's agent-type sub-menu (there is no bare "Terminal" agent
type), so the test registers a minimal echoing program and drives that.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import expect_chat_replaces_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import type_with_global_keyboard
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A registered terminal program: it banners (the "PTY is up" signal), then echoes
# each stdin line — enough of a TUI stand-in for a focus test, since the PTY's
# canonical-mode echo shows typed characters in the buffer as they arrive. The
# banner is assembled with printf so the wait can't match the launch command's
# own echo in the buffer (a plain `echo TERM-FOCUS-READY` would).
_FOCUS_PROGRAM_COMMAND = "printf %sREADY TERM-FOCUS-; echo; while read -r _line; do echo GOT:$_line; done"


@user_story("to start typing in a terminal agent immediately after selecting its panel tab")
def test_terminal_agent_tab_switch_focuses_terminal(sculptor_instance_: SculptorInstance) -> None:
    """Selecting a terminal agent's panel tab auto-focuses its terminal pane.

    Steps:
    1. Create a workspace with a chat agent (one agent panel tab in center).
    2. Create a registered terminal agent from the agent-type sub-menu (tab 2);
       creating it activates the new tab.
    3. Switch away to the chat agent — the terminal pane unmounts and gives up
       keyboard focus.
    4. Switch back to the terminal agent's tab.
    5. The terminal pane must hold keyboard focus, and a probe typed with the
       global keyboard (which routes to ``document.activeElement``) must land in
       the xterm buffer — proving typing works without clicking into the pane.
    """
    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    registration = registrations_dir / "focus-term.toml"
    registration.write_text(f'display_name = "Focus Term"\nlaunch_command = "{_FOCUS_PROGRAM_COMMAND}"\n')

    page = sculptor_instance_.page
    try:
        start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Focus WS")
        panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
        agent_tabs = panel_tabs.get_agent_tabs()
        expect(agent_tabs).to_have_count(1)

        # Create the terminal agent; creation activates its tab, so the agent
        # terminal panel mounts in place of the chat.
        dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
        dropdown.open()
        dropdown.open_agent_type_submenu()
        registered_item = dropdown.get_agent_type_item_registered("focus-term")
        expect(registered_item).to_be_visible()
        registered_item.click()

        expect(agent_tabs).to_have_count(2)
        terminal_tab = panel_tabs.get_panel_tab_by_name("Focus Term 1").first
        expect(terminal_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        # The program's banner is the deterministic "shell is up" signal — the
        # backend PTY may still be spawning when the panel mounts.
        wait_for_xterm_substring(page, "TERM-FOCUS-READY")

        # Switch away to the chat agent — the terminal pane unmounts (chat input
        # replaces it), so the terminal no longer owns keyboard focus.
        agent_tabs.first.click()
        expect_chat_replaces_terminal_panel(page)

        # Switch back to the terminal agent's tab.
        terminal_tab.click()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        agent_terminal_textarea = get_agent_terminal_textarea(page)
        expect(agent_terminal_textarea).to_be_attached()

        # The terminal pane must auto-focus on tab switch (SCU-1578). Without the
        # fix the freshly-mounted panel never grabs focus, so the user has to click
        # into it before typing.
        expect(agent_terminal_textarea).to_be_focused()

        # Prove the user-facing guarantee, not just the focus snapshot: type a probe
        # with the GLOBAL keyboard (routes to document.activeElement) and confirm it
        # reaches the program's PTY. The leading throwaway chars absorb any
        # keystrokes xterm may drop right as input begins.
        probe_marker = "TAB_SWITCH_FOCUS_OK"
        type_with_global_keyboard(page, "zzz " + probe_marker)
        wait_for_xterm_substring(page, probe_marker)
    finally:
        registration.unlink(missing_ok=True)
