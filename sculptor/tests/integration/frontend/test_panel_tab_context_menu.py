"""Integration tests for the shared panel-tab context menu (PANEL-07/11/14, AGENT-06, TERM-02).

The redesigned shell renders ONE context menu for every panel tab (agent and
terminal alike): Rename for multi-instance panels (PANEL-11), plus — for agents — the
flat diagnostics copy items (AGENT-06: copy agent id / name, copy claude session id /
transcript paths, disabled until a session exists). Closing a tab routes through the
close (X) button to a confirmation dialog (AGENT-04 / TERM-02).

These cases are CREATE-not-migrate (per `03_07_agent_terminal_panel_tests.md`): they
consolidate `test_agent_tab_context_menu.py`, `test_agent_diagnostics_context_menu.py`,
and the rename/context halves of `test_terminal_tab_enhancements.py` /
`test_tab_context_menus.py` onto the panel-tab model. Task 8.2 deletes the superseded
files.

Known phase gaps applied here (the redesigned PanelTab context menu does not yet carry
these affordances — the old agent tab bar did):
* Diagnostics is a FLAT set of copy items (no "Diagnostics" sub-menu), so items are
  asserted by their visible label rather than a per-item testid.
* Mark-unread (AGENT-07) and the status-dot `data-dot-status` reader are not wired on
  the panel tab — skipped.
* Close-others is not offered on the panel-tab context menu — skipped.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.clipboard import reset_intercepted_clipboard
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_MARK_UNREAD_SKIP_REASON = "Mark-unread (AGENT-07) and the status-dot data-dot-status reader are not wired on the redesigned panel tab's context menu (the dot renders but carries no testable attribute, and there is no Mark-unread item); deferred to a later task."

_CLOSE_OTHERS_SKIP_REASON = "Close-others is not offered on the redesigned panel-tab context menu (only Rename + diagnostics copy items render); deferred to a later task."


@user_story("to rename an agent panel tab but not close it via a dedicated menu item")
def test_agent_tab_offers_rename(sculptor_instance_: SculptorInstance) -> None:
    """An agent panel tab's context menu offers Rename and starts an inline edit (PANEL-11)."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Rename menu agent", workspace_name="Rename Menu WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_tabs.rename_tab_via_context_menu(tabs.nth(1), "Renamed Agent")
    # The inline rename input is dismissed on commit (the persisted label change is
    # wired to the data layer in a later task; here we assert the affordance works).
    expect(panel_tabs.get_inline_rename_input()).not_to_be_visible()


@user_story("to rename a terminal panel tab via double-click")
def test_terminal_tab_double_click_rename(sculptor_instance_: SculptorInstance) -> None:
    """Double-clicking a terminal panel tab starts an inline rename (PANEL-11)."""
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Rename WS")
    create_terminal_panel(page, section="bottom")

    terminal_tab = bottom_tabs.get_panel_tab_by_name("Terminal 1")
    expect(terminal_tab).to_have_count(1)
    terminal_tab.dblclick()
    expect(bottom_tabs.get_inline_rename_input()).to_be_visible()


@user_story("to copy an agent's id from its tab context menu")
def test_agent_tab_copy_agent_id(sculptor_instance_: SculptorInstance) -> None:
    """The agent tab context menu copies the agent id (always available, no session needed)."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Copy id agent", workspace_name="Copy Id WS")
    install_clipboard_interceptor(page)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)
    panel_tabs.open_context_menu(tabs.first)

    copy_agent_id = panel_tabs.get_diagnostics_item_by_text("Copy agent id")
    expect(copy_agent_id).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_agent_id.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    agent_id = read_intercepted_clipboard(page)
    assert agent_id, "Expected the agent id to be copied to the clipboard"


@user_story("to see diagnostics copy items disabled for an agent with no session")
def test_agent_tab_diagnostics_disabled_without_session(sculptor_instance_: SculptorInstance) -> None:
    """The session/transcript copy items are disabled for an agent that has not run.

    A freshly-added second agent has no session yet, so "Copy claude session id" is
    disabled (Radix marks disabled items with ``data-disabled``).
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Has session", workspace_name="Diag Disabled WS")
    # The second agent has no session yet.
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_tabs.open_context_menu(tabs.nth(1))
    copy_session_id = panel_tabs.get_diagnostics_item_by_text("Copy claude session id")
    expect(copy_session_id).to_be_visible()
    expect(copy_session_id).to_have_attribute("data-disabled", "")


@user_story("to close an agent from its tab with a confirmation")
def test_agent_tab_close_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing an agent panel tab surfaces the delete confirmation (AGENT-04)."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Close confirm agent", workspace_name="Close Confirm Menu WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    second_tab = tabs.nth(1)
    testid = second_tab.get_attribute("data-testid")
    assert testid is not None and testid.startswith("PANEL_TAB-")
    panel_id = testid[len("PANEL_TAB-") :]

    second_tab.click()
    panel_tabs.get_tab_close_button(panel_id).click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_visible()
    panel_tabs.get_delete_confirmation_confirm_button().click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(tabs).to_have_count(1)


@pytest.mark.skip(reason=_MARK_UNREAD_SKIP_REASON)
@user_story("to mark an agent unread from its tab context menu")
def test_agent_tab_mark_unread(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder for AGENT-07: mark-unread + the status-dot reader are not wired on
    the redesigned panel tab's context menu."""


@pytest.mark.skip(reason=_CLOSE_OTHERS_SKIP_REASON)
@user_story("to close other terminal tabs from a terminal tab context menu")
def test_terminal_tab_close_others(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder for PANEL-14 close-others, which the redesigned panel-tab context
    menu does not yet offer."""
