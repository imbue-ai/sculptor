"""Integration tests for the "Mark as unread" context-menu action on agent panel tabs.

Marking an agent unread flips its tab's status dot to unread and suppresses the
auto mark-read while the user keeps viewing the agent. The unread state ends on a
fresh activation of the agent (switching back onto it) or when a new agent turn
arrives.

These tests verify:
- Marking the viewed agent tab unread does NOT auto-revert to read
- Marking an adjacent (non-active) agent tab unread works
- Marking unread then leaving/returning to the workspace marks it read
- Unread persists on a non-focused agent across workspace switches
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

SECONDS_MS = 1000


def _mark_tab_unread(page: Page, panel_tabs: PlaywrightPanelTabElement, tab: Locator) -> None:
    """Open a tab's context menu and click its "Mark as unread" item."""
    panel_tabs.open_context_menu(tab)
    mark_unread_item = panel_tabs.get_context_menu_mark_unread_item()
    expect(mark_unread_item).to_be_visible()
    mark_unread_item.click()


def _get_tab_status_dot(tab: Locator) -> Locator:
    """The rendered status-dot element inside an agent panel tab.

    Agent tabs render a visible dot whose ``data-panel-tab-dot`` attribute carries
    the same status as the tab's ``data-dot-status``.
    """
    return tab.get_by_test_id(ElementIDs.PANEL_TAB_STATUS_DOT)


@user_story("to mark the viewed agent tab as unread without it reverting")
def test_mark_active_tab_unread_stays_unread(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark the currently viewed agent tab as unread and verify it stays unread.

    The unread override suppresses useMarkRead's debounced auto mark-read, and no
    new agent turn arrives after the action, so the dot must stay unread even
    though the user is still viewing the agent.

    Steps:
    1. Create a workspace with an agent, wait for it to finish
    2. Verify the agent shows as read
    3. Right-click the active agent tab and select "Mark as unread"
    4. Verify the tab and its rendered dot show unread
    5. Wait longer than the useMarkRead debounce (1s) to confirm it stays unread
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    # Step 1: Create workspace with an agent.
    task_page = start_task_and_wait_for_ready(page, prompt="Active tab test", workspace_name="Active Unread WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Step 2: Verify agent is read.
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)
    expect(tabs.first).to_have_attribute("data-dot-status", "read")

    # Step 3: Mark the active agent tab as unread.
    _mark_tab_unread(page, panel_tabs, tabs.first)

    # Step 4: The tab carries the unread state and renders a visible unread dot.
    expect(tabs.first).to_have_attribute("data-dot-status", "unread")
    status_dot = _get_tab_status_dot(tabs.first)
    expect(status_dot).to_be_visible()
    expect(status_dot).to_have_attribute("data-panel-tab-dot", "unread")

    # Step 5: Wait 3 seconds (well beyond the 1s debounce) and confirm it stays unread.
    page.wait_for_timeout(3 * SECONDS_MS)
    expect(tabs.first).to_have_attribute("data-dot-status", "unread")


@user_story("to mark an adjacent agent tab as unread")
def test_mark_adjacent_tab_unread(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark a non-active agent tab as unread via the context menu.

    Steps:
    1. Create a workspace with two agents
    2. Ensure agent 2 is active and both are read
    3. Right-click agent 1 (not active) and select "Mark as unread"
    4. Verify agent 1 shows unread and agent 2 stays read
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    # Step 1: Create workspace with agent 1.
    task_page = start_task_and_wait_for_ready(page, prompt="Adjacent tab test", workspace_name="Adjacent Unread WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Add agent 2 (opens as the active center tab).
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    # Send a message on agent 2 so it has activity and shows as read.
    chat_panel = PlaywrightTaskPage(page=page).get_chat_panel()
    send_chat_message(chat_panel, "Do something on agent 2")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Visit agent 1 to mark it read, then return to agent 2.
    tabs.first.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()
    tabs.last.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()

    # Step 2: Both agents should be read.
    expect(tabs.first).to_have_attribute("data-dot-status", "read")
    expect(tabs.last).to_have_attribute("data-dot-status", "read")

    # Step 3: Right-click agent 1 (not active) and mark unread.
    _mark_tab_unread(page, panel_tabs, tabs.first)

    # Step 4: Agent 1 should be unread, agent 2 should still be read.
    expect(tabs.first).to_have_attribute("data-dot-status", "unread")
    expect(_get_tab_status_dot(tabs.first)).to_have_attribute("data-panel-tab-dot", "unread")
    expect(tabs.last).to_have_attribute("data-dot-status", "read")


@user_story("to see a marked-unread agent become read when returning to its workspace")
def test_mark_unread_then_leave_and_return_marks_read(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark an agent unread, leave the workspace, return, and verify it becomes read.

    Returning to the workspace is a fresh activation of its focused agent, which
    clears the explicit unread state and marks the agent read.

    Steps:
    1. Create workspace A with an agent, wait for it to finish
    2. Create workspace B (navigates away from A)
    3. Navigate back to workspace A, verify agent is read
    4. Mark agent in workspace A as unread
    5. Navigate to workspace B
    6. Navigate back to workspace A
    7. Verify agent is now read (useMarkRead fired on the fresh activation)
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    # Step 1: Create workspace A.
    task_page_a = start_task_and_wait_for_ready(page, prompt="WS A agent", workspace_name="Workspace A")
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel_a, expected_message_count=2)

    # Step 2: Create workspace B.
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    workspace_rows = get_workspace_sidebar(page).get_workspace_rows()
    expect(workspace_rows).to_have_count(2)

    # Step 3: Navigate to workspace A.
    workspace_rows.first.click()
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)
    expect(tabs.first).to_have_attribute("data-dot-status", "read")

    # Step 4: Mark agent in workspace A as unread.
    _mark_tab_unread(page, panel_tabs, tabs.first)
    expect(tabs.first).to_have_attribute("data-dot-status", "unread")

    # Step 5: Navigate to workspace B.
    workspace_rows.last.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()

    # Step 6: Navigate back to workspace A.
    workspace_rows.first.click()
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    # Step 7: Agent should be read (useMarkRead fired when workspace A re-mounted).
    expect(tabs.first).to_have_attribute("data-dot-status", "read")


@user_story("to see an unread agent persist across workspace switches when not focused")
def test_unread_persists_on_unfocused_agent_across_workspace_switches(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark agent 1 unread, switch to agent 2, leave and return to the workspace on
    agent 2, and verify agent 1 still shows unread. Then navigate to agent 1 and
    verify it becomes read.

    The unread state is persisted (the server clears the agent's last-read
    timestamp), so it survives leaving the workspace as long as the agent is not
    activated again.

    Steps:
    1. Create workspace A with agent 1, wait for it to finish
    2. Add agent 2 to workspace A, send a message so it has activity
    3. Switch to agent 1, then back to agent 2 so both are read
    4. Mark agent 1 unread (while on agent 2)
    5. Create workspace B (navigates away from workspace A)
    6. Navigate back to workspace A (lands on agent 2, the last active agent)
    7. Verify agent 1 still shows unread (it was never focused)
    8. Click agent 1, verify it becomes read
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    # Step 1: Create workspace A with agent 1.
    task_page = start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Workspace A")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    # Step 2: Add agent 2 (opens as the active center tab).
    create_agent_panel(page, section="center")
    expect(tabs).to_have_count(2)

    # Send a message on agent 2 so it has response activity.
    chat_panel = PlaywrightTaskPage(page=page).get_chat_panel()
    send_chat_message(chat_panel, "Do something on agent 2")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Step 3: Switch to agent 1 then back to agent 2 so both are read.
    tabs.first.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()
    tabs.last.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()

    expect(tabs.first).to_have_attribute("data-dot-status", "read")
    expect(tabs.last).to_have_attribute("data-dot-status", "read")

    # Step 4: Mark agent 1 unread (while viewing agent 2).
    _mark_tab_unread(page, panel_tabs, tabs.first)
    expect(tabs.first).to_have_attribute("data-dot-status", "unread")

    # Step 5: Create workspace B (navigates away from workspace A).
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    workspace_rows = get_workspace_sidebar(page).get_workspace_rows()
    expect(workspace_rows).to_have_count(2)

    # Step 6: Navigate back to workspace A (restores the layout, active on agent 2).
    workspace_rows.first.click()
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    # Step 7: Agent 1 should still be unread (we returned to agent 2, not agent 1).
    expect(tabs.first).to_have_attribute("data-dot-status", "unread")
    # Agent 2 should be read (useMarkRead fired for the focused agent).
    expect(tabs.last).to_have_attribute("data-dot-status", "read")

    # Step 8: Click agent 1, verify it becomes read.
    tabs.first.click()
    expect(tabs.first).to_have_attribute("data-dot-status", "read")
