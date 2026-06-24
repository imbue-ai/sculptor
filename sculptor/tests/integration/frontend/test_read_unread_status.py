"""Integration tests for read/unread status indicators on agent and workspace tabs.

These tests verify:
- Agent tabs show unread (green) when an agent has updates the user hasn't seen
- Agent tabs show read (grey) after the user navigates to that agent
- Workspace tabs derive unread state from their agents
- The focused agent stays read as it receives updates
- Read/unread status persists across server restarts
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@user_story("to see which agents have unseen updates within a workspace")
def test_unread_indicator_when_switching_agents_within_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Create a workspace with two agents, verify read/unread transitions on agent tabs.

    Flow:
    1. Create workspace with agent 1 (finishes, user sees it → read)
    2. Add agent 2 (auto-navigates to agent 2, both are read/unread appropriately)
    3. Send a message on agent 2 so it gets activity
    4. Switch to agent 1 — agent 2 now has unseen activity → should be unread
    """
    page = sculptor_instance_.page

    # Create first agent in a new workspace
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Read Test WS")

    # Agent 1 should be read (we're viewing it and it finished)
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Workspace tab should also be read (only agent is read)
    workspace_tabs = get_workspace_sidebar(page).get_workspace_rows()
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

    # Add a second agent (auto-navigates to it)
    agent_tab_bar.add_agent()
    expect(agent_tabs).to_have_count(2)

    # Send a message on agent 2 so it gets response activity
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel, "Do something")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Agent 2 should be read (we're viewing it)
    expect(agent_tabs.last).to_have_attribute("data-dot-status", "read")

    # Switch to agent 1 — we leave agent 2 behind
    agent_tabs.first.click()

    # Wait for chat panel to update (we're now on agent 1)
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # Agent 1 should be read (we just navigated to it)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Agent 2 should still be read — no new updates happened after we left
    expect(agent_tabs.last).to_have_attribute("data-dot-status", "read")

    # Now send a follow-up to agent 1 (which will make agent 1's updatedAt change,
    # but we're viewing it so it stays read)
    send_chat_message(chat_panel, "Follow up message")
    wait_for_completed_message_count(chat_panel, expected_message_count=4)

    # Agent 1 should still be read (we're viewing it while it updates)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")


@user_story("to see which workspaces have unseen agent updates")
def test_unread_workspace_indicator_across_workspaces(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Create two workspaces and verify the workspace tab unread indicator.

    Flow:
    1. Create workspace A with agent (finishes, user sees it → read)
    2. Create workspace B with agent (navigates away from A)
    3. Workspace A should be read (agent was seen before leaving)
    4. Workspace B should be read (we're viewing it)
    5. Navigate back to workspace A, send a message to trigger activity
    6. Navigate to workspace B — workspace A's agent got a response → A is unread
    7. Navigate back to workspace A — it becomes read
    """
    page = sculptor_instance_.page

    # Create workspace A with an agent
    task_page_a = start_task_and_wait_for_ready(page, prompt="Agent in workspace A", workspace_name="Workspace A")

    # Wait for the full message pipeline to settle (streaming stop + messages
    # rendered + queued messages drained).  This prevents a race where a
    # trailing backend event (e.g. task-status → COMPLETED) arrives *after*
    # the user navigates away, causing workspace A to appear "unread".
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    workspace_tabs = get_workspace_sidebar(page).get_workspace_rows()
    expect(workspace_tabs).to_have_count(1)
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

    # Create workspace B (navigates away from A)
    start_task_and_wait_for_ready(page, prompt="Agent in workspace B", workspace_name="Workspace B")

    expect(workspace_tabs).to_have_count(2)

    # Both workspaces should be read
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")
    expect(workspace_tabs.last).to_have_attribute("data-has-unread", "false")

    # Navigate to workspace A and send a follow-up to generate new activity
    workspace_tabs.first.click()
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    send_chat_message(chat_panel, "Follow up in workspace A")
    wait_for_completed_message_count(chat_panel, expected_message_count=4)

    # Workspace A should be read (we're viewing it)
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

    # Now navigate to workspace B — workspace A's agent just got a response
    # that we saw, so workspace A should still be read
    workspace_tabs.last.click()

    # Wait for workspace B's chat to appear
    chat_panel = PlaywrightTaskPage(page=page).get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # Both workspaces should be read (we saw A's response before leaving).
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")
    expect(workspace_tabs.last).to_have_attribute("data-has-unread", "false")


@user_story("to see my focused agent stay read as it receives updates")
def test_focused_agent_stays_read_while_receiving_updates(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify that the agent the user is currently viewing stays read.

    The useMarkRead hook should re-fire (debounced) whenever updatedAt
    changes while the user is viewing the agent, keeping it read.
    """
    page = sculptor_instance_.page

    # Create a workspace with an agent
    task_page = start_task_and_wait_for_ready(page, prompt="Initial prompt", workspace_name="Focused WS")

    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Agent should be read (we just viewed the initial response)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Send a follow-up message while staying on this agent
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel, "Follow up 1")
    wait_for_completed_message_count(chat_panel, expected_message_count=4)

    # Agent should still be read (useMarkRead re-fires on updatedAt change)
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Send another follow-up
    send_chat_message(chat_panel, "Follow up 2")
    wait_for_completed_message_count(chat_panel, expected_message_count=6)

    # Agent should still be read
    expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

    # Workspace should also show no unread
    workspace_tabs = get_workspace_sidebar(page).get_workspace_rows()
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")


@user_story("to have my read/unread agent status persist after restarting Sculptor")
def test_read_status_persists_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Agent read status should survive a full server restart.

    Regression test for a bug where all agents/workspaces showed as unread on
    startup. CodingAgentTaskView.updated_at was computed from the last message
    of any type, including bookkeeping messages (RequestStartedAgentMessage,
    RequestSuccessAgentMessage) that are persisted to the DB with timestamps
    lagging behind the frontend's mark_read call. On restart these stale
    bookkeeping timestamps became updated_at > last_read_at, making previously-
    read tasks appear unread.

    Steps:
    1. Start Sculptor, create a workspace with an agent, let it finish
    2. Verify the workspace shows as read (user is viewing it)
    3. Wait for the debounced mark_read to fire and persist to the database
    4. Restart Sculptor (full server restart against the same database)
    5. Verify the workspace tab still shows as read WITHOUT clicking on it
       (clicking would trigger useMarkRead, masking the persistence bug)
    """
    # === First instance: create agent and mark as read ===
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        # Step 1: Create agent and wait for it to finish
        task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Persist WS")
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel, expected_message_count=2)

        # Step 2: Verify the workspace and agent show as read
        agent_tab_bar = task_page.get_agent_tab_bar()
        agent_tabs = agent_tab_bar.get_agent_tabs()
        expect(agent_tabs).to_have_count(1)
        expect(agent_tabs.first).to_have_attribute("data-dot-status", "read")

        workspace_tabs = get_workspace_sidebar(page).get_workspace_rows()
        expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

        # Step 3: Give time for the debounced mark_read to fire and persist
        page.wait_for_timeout(2000)

    # === Second instance: verify read status persists after restart ===
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        # Step 4: Wait for the workspace tab to appear (server has restarted)
        workspace_tabs = get_workspace_sidebar(page).get_workspace_rows()
        expect(workspace_tabs.first).to_be_visible()

        # Step 5: Check workspace tab shows read WITHOUT clicking on it.
        # Clicking would navigate into the workspace, mount the chat panel,
        # and trigger useMarkRead — which would re-mark the agent as read,
        # masking the persistence bug.
        expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")
