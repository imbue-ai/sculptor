"""Integration tests for the agent panel.

Agents render as panel tabs in the center section, created from the section `+`
add-panel dropdown (or the workspace-create flow). This file owns the agent-panel
TAB-MODEL behaviour: the chat is preserved across panel switches, two agents can
render side by side across sections, closing an agent surfaces a delete
confirmation, closing the LAST agent leaves the center section empty (no
auto-create), and a multi-instance panel tab offers inline rename.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_empty_state import PlaywrightEmptySectionState
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


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

    # The intro banner names THIS panel's agent. Creating the second agent moved
    # the route to it, and tab activation doesn't navigate — so a route-derived
    # identity would name the second agent here instead of the panel's own.
    first_tab_label = panel_tabs.get_panel_tab(first_panel_id).inner_text()
    expect(get_alpha_chat_view(page).get_intro()).to_contain_text(first_tab_label)


@user_story("to view two agents side by side in the center and right sections")
def test_agent_in_center_and_right_at_once(sculptor_instance_: SculptorInstance) -> None:
    """Two agents rendered at once — one in center, one in the right section.

    The first agent comes from the workspace-create flow (center). The second is
    added from the right section's `+` add-panel dropdown, which lands it in the
    right section. Both agent panels stay mounted side by side: each section keeps
    its own agent tab and renders its own chat panel.
    """
    page = sculptor_instance_.page
    center_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    right_tabs = PlaywrightPanelTabElement(page, sub_section="right")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Center And Right WS")
    expect(center_tabs.get_panel_tabs()).to_have_count(1)

    # Expand the (empty) right section and add an agent from its `+` dropdown.
    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    right_dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="right")
    right_dropdown.open()
    new_agent_item = right_dropdown.get_new_agent_item()
    expect(new_agent_item).to_be_visible()
    new_agent_item.click()

    # The new agent lands in the right section; the center keeps its own agent.
    expect(right_tabs.get_panel_tabs()).to_have_count(1)
    expect(center_tabs.get_panel_tabs()).to_have_count(1)

    # Both agents render at once: each section hosts its own mounted chat panel.
    center_chat = PlaywrightWorkspaceSection(page, "center").get_section().get_by_test_id(ElementIDs.CHAT_PANEL)
    right_chat = right.get_section().get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(center_chat).to_be_visible()
    expect(right_chat).to_be_visible()


@user_story("to delete an agent by closing its tab, with a confirmation")
def test_closing_agent_tab_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing an agent panel tab opens a delete confirmation; confirming removes it.

    Closing is a destructive delete, not a hide — it surfaces the delete
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
    panel_tabs.get_tab_close_button_of(second_tab).click()
    dialog = panel_tabs.get_delete_confirmation_dialog()
    expect(dialog).to_be_visible()
    panel_tabs.get_delete_confirmation_cancel_button().click()
    expect(dialog).to_be_hidden()
    expect(tabs).to_have_count(2)

    # Confirming removes the agent.
    panel_tabs.get_tab_close_button_of(second_tab).click()
    confirm_button = panel_tabs.get_delete_confirmation_confirm_button()
    expect(confirm_button).to_be_visible()
    confirm_button.click()
    expect(dialog).to_be_hidden()
    expect(tabs).to_have_count(1)


@user_story("to not have a replacement agent auto-created when I close my last one")
def test_closing_last_agent_does_not_auto_create(sculptor_instance_: SculptorInstance) -> None:
    """Closing the last agent does NOT auto-create a replacement.

    Deleting the last agent leaves the center section empty — no replacement agent
    panel tab is created to refill it.
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Last agent", workspace_name="Empty Center WS")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    only_tab = tabs.first
    only_tab.click()
    panel_tabs.get_tab_close_button_of(only_tab).click()
    confirm_button = panel_tabs.get_delete_confirmation_confirm_button()
    expect(confirm_button).to_be_visible()
    confirm_button.click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()

    # Assert on the settled empty state before the tab count: an empty center is also
    # transiently true in the gap before an auto-created replacement would land, so
    # waiting for the empty-state launcher first makes "no auto-create" a real
    # observation rather than a snapshot of that gap.
    expect(PlaywrightEmptySectionState(page, "center").get_add_panel_button()).to_be_visible()
    expect(panel_tabs.get_panel_tabs()).to_have_count(0)


@user_story("to rename an agent from its panel tab")
def test_agent_tab_offers_rename_for_multiple_instances(sculptor_instance_: SculptorInstance) -> None:
    """An agent panel tab offers inline rename (a multi-instance panel affordance).

    Renaming is a multi-instance affordance: the context menu exposes Rename and an
    inline edit input appears. This asserts only that the rename affordance is
    offered; committed-label persistence is covered elsewhere.
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
