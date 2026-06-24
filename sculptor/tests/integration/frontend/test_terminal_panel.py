"""Integration tests for the terminal as a panel (TERM-01..03).

Terminals render as panel tabs created from the same section `+` add-panel dropdown
as agents. This file owns the terminal TAB-MODEL behaviour: create a terminal panel,
create multiple, switch between them, lowest-available-number reuse after close
(TERM-03), and close = a confirmation dialog (TERM-02 — terminal close had no
confirmation before; goals.md adds one).

These cases are CREATE-not-migrate (per `03_07_agent_terminal_panel_tests.md`): they
supersede the add / switch / close / numbering TAB-MODEL half of `test_terminal.py`,
re-anchored onto the panel-tab model and the new add-panel dropdown. The xterm I/O
(CONTENT) tests stay in `test_terminal.py`; Task 8.2 finishes that split.

A terminal lands in the bottom section, which is collapsed by default — the
``create_terminal_panel`` helper expands it first via the workspace header toggle.
"""

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
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
    """Creating a terminal via the bottom section `+` adds a "Terminal 1" panel tab."""
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Panel WS")

    create_terminal_panel(page, section="bottom")

    terminal_tab = bottom_tabs.get_panel_tab_by_name("Terminal 1")
    expect(terminal_tab).to_have_count(1)


@user_story("to run multiple terminals and switch between them")
def test_multiple_terminal_panels_and_switch(sculptor_instance_: SculptorInstance) -> None:
    """Two terminal panels can coexist; clicking a tab makes it the active one."""
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Multi Terminal WS")

    create_terminal_panel(page, section="bottom")
    create_terminal_panel(page, section="bottom")

    expect(bottom_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(1)
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(1)

    # Terminal 2 was created last, so it is active; switch to Terminal 1.
    first_terminal = bottom_tabs.get_panel_tab_by_name("Terminal 1")
    first_terminal.click()
    expect(bottom_tabs.get_active_tab()).to_contain_text("Terminal 1")

    # Switch back to Terminal 2.
    bottom_tabs.get_panel_tab_by_name("Terminal 2").click()
    expect(bottom_tabs.get_active_tab()).to_contain_text("Terminal 2")


@user_story("to be asked to confirm before closing a terminal")
def test_closing_terminal_panel_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing a terminal panel tab opens a close confirmation (TERM-02).

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

    Create Terminal 1 + Terminal 2, close Terminal 1, then create a new terminal —
    it is named "Terminal 1" again (lowest available), not "Terminal 3" (TERM-03).
    """
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Numbering WS")

    create_terminal_panel(page, section="bottom")
    create_terminal_panel(page, section="bottom")
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(1)
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(1)

    # Close Terminal 1.
    terminal_one = bottom_tabs.get_panel_tab_by_name("Terminal 1")
    bottom_tabs.delete_panel_via_close_button(_panel_id_of(terminal_one))
    expect(bottom_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(0)

    # The next terminal reuses number 1 (lowest available), not 3.
    create_terminal_panel(page, section="bottom")
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(1)
    expect(bottom_tabs.get_panel_tab_by_name("Terminal 3")).to_have_count(0)
