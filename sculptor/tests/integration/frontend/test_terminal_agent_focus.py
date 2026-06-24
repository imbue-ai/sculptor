"""Regression test: switching to a terminal agent's tab must focus its pane.

A terminal agent's main panel is a PTY terminal that occupies the chat space.
The terminal is the agent's only input surface, so selecting its tab should
place keyboard focus into the terminal immediately — the user must be able to
type without first clicking into the pane (SCU-1578).
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.terminal import expect_chat_replaces_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import type_with_global_keyboard
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


@user_story("to start typing in a terminal agent immediately after selecting its tab")
def test_terminal_agent_tab_switch_focuses_terminal(sculptor_instance_: SculptorInstance) -> None:
    """Selecting a terminal agent's tab auto-focuses its terminal pane.

    Steps:
    1. Create a workspace with a chat agent (tab 1).
    2. Create a terminal agent (tab 2); creating it navigates to the new tab.
    3. Switch away to the chat agent — the terminal pane unmounts and gives up
       keyboard focus.
    4. Switch back to the terminal agent's tab.
    5. The terminal pane must hold keyboard focus, and a probe typed with the
       global keyboard (which routes to ``document.activeElement``) must land in
       the xterm buffer — proving typing works without clicking into the pane.
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Focus WS")
    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    _create_terminal_agent(agent_tab_bar)
    expect(agent_tabs).to_have_count(2)
    terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
    expect(terminal_tab).to_be_visible()
    _wait_for_terminal_ready(page)

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
    # reaches the shell. The leading throwaway chars absorb any keystrokes xterm
    # may drop right as input begins.
    probe_marker = "TAB_SWITCH_FOCUS_OK"
    type_with_global_keyboard(page, "zzz " + probe_marker)
    wait_for_xterm_substring(page, probe_marker)
