"""Integration tests for the agent panel (AGENT-01..04, PANEL-11).

Agents render as panel tabs in the center section, created from the section `+`
add-panel dropdown (or the workspace-create flow). This file owns the agent-panel
TAB-MODEL behaviour: the chat is preserved across switches, zero/one/multiple agents,
closing an agent = a delete confirmation, and closing the LAST agent leaves the
center section empty (Decision B1 — no auto-create).

These cases are CREATE-not-migrate (per `03_07_agent_terminal_panel_tests.md`): they
supersede the agent-count / multi-agent / survive-deleted / lowest-number-reuse
kernels of `test_multi_agent_workspace.py`, re-anchored onto the panel-tab model and
the new add-panel dropdown. Task 8.2 deletes the superseded file; this task only
creates the replacement.

Known phase gaps applied here:
* An agent in the center AND the right section at once (AGENT-03) needs the
  drag/move-to-section affordance, which is not wired until Task 4.1 — skipped.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_AGENT_IN_RIGHT_SKIP_REASON = "An agent in center + right at once (AGENT-03) needs the drag / move-to-section affordance, which is not wired until Task 4.1; new agents always land in center and there is no UI to relocate them yet."


@user_story("to keep the agent chat mounted while I switch panels")
def test_agent_chat_is_preserved(sculptor_instance_: SculptorInstance) -> None:
    """The agent's chat content survives switching away to another panel and back.

    Send a message, switch the center to a freshly-created second agent, switch back
    to the first agent's tab, and verify the first agent's chat still shows both
    messages (the panel content is not torn down on switch).
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Chat Preserved WS")
    first_agent_id = task_page.get_task_id()
    first_panel_id = f"agent:{first_agent_id}"

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Add a second agent (lands in center, becomes active) — the first agent's chat
    # is no longer the active panel.
    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(2)

    # Switch back to the first agent's tab; its chat remounts with both messages.
    panel_tabs.get_panel_tab(first_panel_id).click()
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)


@user_story("to see exactly one agent tab for a single-agent workspace")
def test_single_agent_shows_one_tab(sculptor_instance_: SculptorInstance) -> None:
    """A workspace created with one agent shows exactly one agent panel tab."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Only agent", workspace_name="Solo Agent WS")

    expect(panel_tabs.get_panel_tabs()).to_have_count(1)


@user_story("to run multiple agents in the same workspace")
def test_multiple_agents_show_multiple_tabs(sculptor_instance_: SculptorInstance) -> None:
    """Adding agents via the `+` dropdown grows the agent panel-tab count."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="First agent", workspace_name="Multi Agent WS")
    expect(panel_tabs.get_panel_tabs()).to_have_count(1)

    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(2)

    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(3)


@pytest.mark.skip(reason=_AGENT_IN_RIGHT_SKIP_REASON)
@user_story("to view two agents side by side in the center and right sections")
def test_agent_in_center_and_right_at_once(sculptor_instance_: SculptorInstance) -> None:
    """Two agents rendered at once — one in center, one in the right section.

    Placeholder for AGENT-03: a new agent always lands in center and there is no UI
    to move/split it into the right section until the drag affordance (Task 4.1)."""


@user_story("to delete an agent by closing its tab, with a confirmation")
def test_closing_agent_tab_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing an agent panel tab opens a delete confirmation; confirming removes it.

    Closing is a destructive delete (AGENT-04), not a hide — it surfaces the delete
    confirmation dialog before the agent is removed.
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Agent to delete", workspace_name="Delete Confirm WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    # Cancelling the confirmation keeps both agents.
    second_tab = tabs.nth(1)
    second_tab.click()
    panel_id = second_tab.get_attribute("data-testid")
    assert panel_id is not None and panel_id.startswith("PANEL_TAB-")
    second_panel_id = panel_id[len("PANEL_TAB-") :]

    panel_tabs.get_tab_close_button(second_panel_id).click()
    dialog = panel_tabs.get_delete_confirmation_dialog()
    expect(dialog).to_be_visible()
    panel_tabs.get_delete_confirmation_cancel_button().click()
    expect(dialog).to_be_hidden()
    expect(tabs).to_have_count(2)

    # Confirming removes the agent.
    panel_tabs.delete_panel_via_close_button(second_panel_id)
    expect(dialog).to_be_hidden()
    expect(tabs).to_have_count(1)


@user_story("to not have a replacement agent auto-created when I close my last one")
def test_closing_last_agent_does_not_auto_create(sculptor_instance_: SculptorInstance) -> None:
    """Closing the last agent does NOT auto-create a replacement (Decision B1).

    The old shell created a fresh agent when the last one was deleted; the redesign
    relaxes that — after the delete there is no agent panel tab (the center is left
    empty rather than refilled).
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Last agent", workspace_name="Empty Center WS")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    only_tab = tabs.first
    panel_id = only_tab.get_attribute("data-testid")
    assert panel_id is not None and panel_id.startswith("PANEL_TAB-")
    only_panel_id = panel_id[len("PANEL_TAB-") :]

    panel_tabs.delete_panel_via_close_button(only_panel_id)
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()

    # No replacement agent panel tab is auto-created.
    expect(panel_tabs.get_panel_tabs()).to_have_count(0)


@user_story("to rename an agent from its panel tab")
def test_agent_tab_offers_rename_for_multiple_instances(sculptor_instance_: SculptorInstance) -> None:
    """An agent panel tab offers inline rename (multi-instance panel, PANEL-11).

    Renaming is a multi-instance affordance: the context menu exposes Rename and an
    inline edit input appears. (The committed-label persistence is wired to the data
    layer in a later task; this asserts the rename affordance is offered.)
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Renamable agent", workspace_name="Rename Agent WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    target = tabs.nth(1)
    panel_tabs.open_context_menu(target)
    rename_item = panel_tabs.get_context_menu_rename_item()
    expect(rename_item).to_be_visible()
    rename_item.click()
    expect(panel_tabs.get_inline_rename_input()).to_be_visible()
