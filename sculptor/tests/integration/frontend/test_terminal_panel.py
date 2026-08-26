"""Integration tests for the terminal as a panel.

Terminals render as panel tabs created from the same section `+` add-panel dropdown
as agents. This file owns the terminal TAB-MODEL behaviour: create a terminal panel,
create multiple, switch between them, lowest-available-number reuse after close,
close = a confirmation dialog (closing a terminal tab requires confirmation), and
per-tab content isolation with scrollback surviving tab switches.

The lowest-available-number reuse scenario lives here on the panel-tab model.
`test_terminal.py` keeps the complementary tab-model cases that also assert
xterm/WebSocket wiring — one WebSocket per added tab, and the active tab switching
to its neighbour on close — alongside its xterm I/O (CONTENT) tests.

A terminal lands in the bottom section, which is collapsed by default — the
``create_terminal_panel`` helper expands it first via the workspace header toggle.
"""

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import get_xterm_buffer_text
from sculptor.testing.elements.terminal import run_command_in_active_terminal
from sculptor.testing.elements.terminal import wait_for_fresh_xterm_buffer
from sculptor.testing.elements.terminal import wait_for_xterm_buffer_nonempty
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _panel_id_of(tab: Locator) -> str:
    """Extract a panel tab's panel id from its ``PANEL_TAB-<panelId>`` testid."""
    testid = tab.get_attribute("data-testid")
    assert testid is not None and testid.startswith("PANEL_TAB-"), f"unexpected tab testid: {testid!r}"
    return testid[len("PANEL_TAB-") :]


@user_story("to open a terminal as a panel from the section + dropdown")
def test_create_terminal_panel(sculptor_instance_: SculptorInstance) -> None:
    """Creating a terminal via the bottom section `+` adds a "Terminal 2" panel tab.

    The default layout seeds Terminal 1 into the bottom section, so the first
    created terminal is Terminal 2. Asserting the seed and the created tab now
    coexist (two tabs total) proves the create actually added a tab rather than
    the assertion passing off the seeded Terminal 1.
    """
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Panel WS")

    create_terminal_panel(page, section="bottom")

    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(1)
    expect(bottom_tabs.get_panel_tabs()).to_have_count(2)


@user_story("to run multiple terminals and switch between them")
def test_multiple_terminal_panels_and_switch(sculptor_instance_: SculptorInstance) -> None:
    """Multiple terminal panels can coexist; clicking a tab makes it the active one.

    Terminal 1 is seeded, so the two creates add Terminal 2 and Terminal 3.
    """
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Multi Terminal WS")

    create_terminal_panel(page, section="bottom")
    create_terminal_panel(page, section="bottom")

    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(1)
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 3")).to_have_count(1)

    # Terminal 3 was created last, so it is active; switch to Terminal 2.
    bottom_tabs.get_panel_tab_by_name("Terminal 2").click()
    expect(bottom_tabs.get_active_tab()).to_contain_text("Terminal 2")

    # Switch back to Terminal 3.
    bottom_tabs.get_panel_tab_by_name("Terminal 3").click()
    expect(bottom_tabs.get_active_tab()).to_contain_text("Terminal 3")


@user_story("to be asked to confirm before closing a terminal")
def test_closing_terminal_panel_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing a terminal panel tab opens a close confirmation.

    Cancelling keeps the terminal; confirming removes it.
    """
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Close WS")

    create_terminal_panel(page, section="bottom")
    terminal_tab = bottom_tabs.get_panel_tab_by_name("Terminal 1")
    expect(terminal_tab).to_have_count(1)
    panel_id = _panel_id_of(terminal_tab)

    # Cancelling the confirmation keeps the terminal.
    terminal_tab.click()
    bottom_tabs.get_tab_close_button(panel_id).click()
    dialog = bottom_tabs.get_delete_confirmation_dialog()
    expect(dialog).to_be_visible()
    bottom_tabs.get_delete_confirmation_cancel_button().click()
    expect(dialog).to_be_hidden()
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(1)

    # Confirming closes the terminal.
    bottom_tabs.delete_panel_via_close_button(panel_id)
    expect(dialog).to_be_hidden()
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(0)


@user_story("to see terminal numbering reuse the lowest available number after a close")
def test_terminal_numbering_reuses_lowest_after_close(sculptor_instance_: SculptorInstance) -> None:
    """Closing a terminal frees its number; the next terminal reuses the lowest free one.

    The default layout seeds Terminal 1 in the bottom section, so created
    terminals start at Terminal 2. Create Terminal 2 + Terminal 3, close
    Terminal 2, then create a new terminal — it is named "Terminal 2" again
    (lowest available), not "Terminal 4".
    """
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Numbering WS")

    # Terminal 1 is seeded; these create Terminal 2 and Terminal 3.
    create_terminal_panel(page, section="bottom")
    create_terminal_panel(page, section="bottom")
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(1)
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 3")).to_have_count(1)

    # Close Terminal 2 (a freed middle number).
    terminal_two = bottom_tabs.get_panel_tab_by_name("Terminal 2")
    bottom_tabs.delete_panel_via_close_button(_panel_id_of(terminal_two))
    expect(bottom_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(0)

    # The next terminal reuses number 2 (lowest available), not 4.
    create_terminal_panel(page, section="bottom")
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(1)
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 4")).to_have_count(0)


@user_story("to see only a terminal's own output in its tab, with scrollback surviving switches")
def test_terminal_content_isolated_and_scrollback_survives_switch(sculptor_instance_: SculptorInstance) -> None:
    """Each terminal panel shows only its own PTY's content, and switching away
    and back retains the scrollback.

    Two terminal panels in one workspace, a distinct marker echoed in each.
    Switching between the tabs must not carry one terminal's scrollback into the
    other (the backend PTYs are isolated per terminal, so any cross-tab text is
    frontend mixing). Switching back replays the first terminal's scrollback and
    the shell still accepts commands — the PTY survived the tab switch (the
    inactive panel unmounts, dropping its WebSocket, but the backend shell and
    its buffer live on).
    """
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Isolation WS")

    # Reveal the seeded Terminal 1 (the bottom section starts collapsed).
    PlaywrightWorkspaceSection(page, "bottom").expand_section()
    first_tab = bottom_tabs.get_panel_tab_by_name("Terminal 1")
    expect(first_tab).to_have_count(1)
    first_tab.click()
    wait_for_xterm_buffer_nonempty(page)
    run_command_in_active_terminal(page, "echo ISOLATION-ALPHA")
    wait_for_xterm_substring(page, "ISOLATION-ALPHA")

    # Creating the second terminal makes it the active tab — a direct
    # terminal -> terminal switch.
    create_terminal_panel(page, section="bottom")
    second_tab = bottom_tabs.get_panel_tab_by_name("Terminal 2")
    expect(second_tab).to_have_count(1)
    # window.__xterm can still reference Terminal 1's handle (whose buffer holds
    # ISOLATION-ALPHA) until its unmount cleanup runs, so wait for a rendered buffer
    # free of ISOLATION-ALPHA — that pins the active xterm to Terminal 2's fresh
    # prompt before the echo runs, rather than typing into an unconnected terminal.
    wait_for_fresh_xterm_buffer(page, "ISOLATION-ALPHA")
    run_command_in_active_terminal(page, "echo ISOLATION-BRAVO")
    wait_for_xterm_substring(page, "ISOLATION-BRAVO")
    assert "ISOLATION-ALPHA" not in get_xterm_buffer_text(page), (
        "Terminal 2 shows Terminal 1's output -- tab contents leaked across terminals"
    )

    # Direct switch back: Terminal 1 replays its own scrollback only. The
    # positive wait proves the replay landed before the negative check reads
    # the buffer.
    first_tab.click()
    wait_for_xterm_substring(page, "ISOLATION-ALPHA")
    assert "ISOLATION-BRAVO" not in get_xterm_buffer_text(page), (
        "Terminal 1 shows Terminal 2's output -- tab contents leaked across terminals"
    )

    # The shell behind Terminal 1 is still live after the switch: a fresh
    # command round-trips. (Only the active tab's xterm is mounted, so the
    # active-terminal typing helper targets Terminal 1 here.)
    run_command_in_active_terminal(page, "echo ALPHA-STILL-ALIVE")
    wait_for_xterm_substring(page, "ALPHA-STILL-ALIVE")
