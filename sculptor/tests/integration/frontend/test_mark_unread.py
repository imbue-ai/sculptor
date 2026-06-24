"""Integration tests for the "Mark unread" context menu action on agent tabs.

These tests verify:
- Marking the active agent tab unread does NOT auto-revert to read
- Marking an adjacent (non-active) agent tab unread works
- Marking unread then leaving/returning to the workspace marks it read
- Unread persists on a non-focused agent across workspace switches
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# The manual "Mark unread" tab action (AGENT-07) is not wired on the redesigned
# panel-tab context menu yet — the dot renders but there is no Mark-unread item
# (the same deferral test_panel_tab_context_menu records). Skip the module until
# that affordance lands; the read/unread-from-activity behaviour is still covered
# by test_read_unread_status.
pytestmark = pytest.mark.skip(reason="Mark-unread tab action (AGENT-07) not yet wired on the redesigned panel tab")

SECONDS_MS = 1000


@user_story("to mark the active agent tab as unread without it reverting")
def test_mark_active_tab_unread_stays_unread(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark the currently focused agent tab as unread and verify it stays unread.

    The useMarkRead hook should NOT re-mark it as read since there are no new
    updatedAt changes after the mark-unread action.

    Steps:
    1. Create a workspace with an agent, wait for it to finish
    2. Verify the agent shows as read
    3. Right-click the active agent tab and select "Mark unread"
    4. Verify the agent shows as unread
    5. Wait longer than the useMarkRead debounce (1s) to confirm it stays unread
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace with an agent.
    task_page = start_task_and_wait_for_ready(page, prompt="Active tab test", workspace_name="Active Unread WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tabs = agent_tab_bar.get_agent_tabs()

    # Step 2: Verify agent is read.
    expect(agent_tabs).to_have_count(1)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Step 3: Mark the active agent tab as unread.
    agent_tab_bar.mark_tab_unread(agent_tabs.first)

    # Step 4: Verify the agent shows as unread.
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "unread")

    # Step 5: Wait 3 seconds (well beyond the 1s debounce) and confirm it stays unread.
    page.wait_for_timeout(3 * SECONDS_MS)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "unread")


@user_story("to mark an adjacent agent tab as unread")
def test_mark_adjacent_tab_unread(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark a non-active agent tab as unread via the context menu.

    Steps:
    1. Create a workspace with two agents
    2. Ensure agent 2 is active and both are read
    3. Right-click agent 1 (not active) and select "Mark unread"
    4. Verify agent 1 shows unread and agent 2 stays read
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace with agent 1.
    task_page = start_task_and_wait_for_ready(page, prompt="Adjacent tab test", workspace_name="Adjacent Unread WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    agent_tab_bar = task_page.get_agent_tab_bar()

    # Add agent 2 (auto-navigates to it).
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Send a message on agent 2 so it has activity and shows as read.
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel, "Do something on agent 2")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Visit agent 1 to mark it read, then return to agent 2.
    agent_tabs.first.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()
    agent_tabs.last.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()

    # Step 2: Both agents should be read.
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")
    expect(agent_tabs.last).to_have_attribute("data-dot-status", "read")

    # Step 3: Right-click agent 1 (not active) and mark unread.
    agent_tab_bar.mark_tab_unread(agent_tabs.first)

    # Step 4: Agent 1 should be unread, agent 2 should still be read.
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "unread")
    expect(agent_tabs.last).to_have_attribute("data-dot-status", "read")


@user_story("to see a marked-unread agent become read when returning to its workspace")
def test_mark_unread_then_leave_and_return_marks_read(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark an agent unread, leave the workspace, return, and verify it becomes read.

    When the user navigates back into a workspace, useMarkRead fires on mount
    for the focused agent, marking it as read.

    Steps:
    1. Create workspace A with an agent, wait for it to finish
    2. Create workspace B (navigates away from A)
    3. Navigate back to workspace A, verify agent is read
    4. Mark agent in workspace A as unread
    5. Navigate to workspace B
    6. Navigate back to workspace A
    7. Verify agent is now read (useMarkRead fired on re-mount)
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace A.
    task_page_a = start_task_and_wait_for_ready(page, prompt="WS A agent", workspace_name="Workspace A")
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel_a, expected_message_count=2)

    agent_tab_bar = task_page_a.get_agent_tab_bar()

    # Step 2: Create workspace B.
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    workspace_tabs = task_page_a.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # Step 3: Navigate to workspace A.
    workspace_tabs.first.click()
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Step 4: Mark agent in workspace A as unread.
    agent_tab_bar.mark_tab_unread(agent_tabs.first)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "unread")

    # Step 5: Navigate to workspace B.
    workspace_tabs.last.click()
    task_page_b = PlaywrightTaskPage(page=page)
    expect(task_page_b.get_chat_panel().get_thinking_indicator()).not_to_be_visible()

    # Step 6: Navigate back to workspace A.
    workspace_tabs.first.click()
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Step 7: Agent should be read (useMarkRead fired when workspace A re-mounted).
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")


@user_story("to see an unread agent persist across workspace switches when not focused")
def test_unread_persists_on_unfocused_agent_across_workspace_switches(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Mark agent 1 unread, switch to agent 2, leave and return to the workspace on
    agent 2, and verify agent 1 still shows unread. Then navigate to agent 1 and
    verify it becomes read.

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

    # Step 1: Create workspace A with agent 1.
    task_page = start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Workspace A")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Step 2: Add agent 2 (auto-navigates to it).
    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tabs).to_have_count(2)

    # Send a message on agent 2 so it has response activity.
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel, "Do something on agent 2")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Step 3: Switch to agent 1 then back to agent 2 so both are read.
    agent_tabs.first.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()
    agent_tabs.last.click()
    expect(PlaywrightTaskPage(page=page).get_chat_panel().get_thinking_indicator()).not_to_be_visible()

    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")
    expect(agent_tabs.last).to_have_attribute("data-dot-status", "read")

    # Step 4: Mark agent 1 unread (while viewing agent 2).
    agent_tab_bar.mark_tab_unread(agent_tabs.first)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "unread")

    # Step 5: Create workspace B (navigates away from workspace A).
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    workspace_tabs = task_page.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # Step 6: Navigate back to workspace A (should land on agent 2, the last active).
    workspace_tabs.first.click()
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Step 7: Agent 1 should still be unread (we returned to agent 2, not agent 1).
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "unread")
    # Agent 2 should be read (useMarkRead fired for the focused agent).
    expect(agent_tabs.last).to_have_attribute("data-dot-status", "read")

    # Step 8: Click agent 1, verify it becomes read.
    agent_tabs.first.click()
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")
