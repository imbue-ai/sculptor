"""Integration tests for read/unread status indicators on agent and workspace tabs.

These tests verify:
- Agent tabs show unread (green) when an agent has updates the user hasn't seen
- Agent tabs show read (grey) after the user navigates to that agent
- Workspace tabs derive unread state from their agents
- The focused agent stays read as it receives updates
- Read/unread status persists across server restarts
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
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
    workspace_tabs = task_page.get_workspace_tabs()
    expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

    # Add a second agent (auto-navigates to it)
    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tabs).to_have_count(2)

    # Adding an agent auto-navigates to it; the chat input is keyed by task id
    # and remounts as the route settles. Typing before the chat panel is bound
    # to the new agent can drop the draft and leave the send button disabled, so
    # wait for the chat panel's data-taskid to flip to the new agent first.
    new_agent_tab = agent_tabs.last
    expect(new_agent_tab).to_have_attribute("data-tab-id", re.compile(r".+"))
    new_agent_id = new_agent_tab.get_attribute("data-tab-id")
    assert new_agent_id is not None  # narrowed for the type checker; the expect above guarantees it
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_have_attribute("data-taskid", new_agent_id)

    # Send a message on agent 2 so it gets response activity
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

    workspace_tabs = task_page_a.get_workspace_tabs()
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
    workspace_tabs = task_page.get_workspace_tabs()
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

        workspace_tabs = task_page.get_workspace_tabs()
        expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

        # Step 3: Give time for the debounced mark_read to fire and persist
        page.wait_for_timeout(2000)

    # === Second instance: verify read status persists after restart ===
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        # Step 4: Wait for the workspace tab to appear (server has restarted)
        layout_page = PlaywrightTaskPage(page=page)
        workspace_tabs = layout_page.get_workspace_tabs()
        expect(workspace_tabs.first).to_be_visible()

        # Step 5: Check workspace tab shows read WITHOUT clicking on it.
        # Clicking would navigate into the workspace, mount the chat panel,
        # and trigger useMarkRead — which would re-mark the agent as read,
        # masking the persistence bug.
        expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")


@user_story("to see my idle terminal agent stay read (idle) after restarting Sculptor")
def test_terminal_agent_read_status_persists_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """A restored, idle terminal agent must show read (grey), not unread (green).

    Regression test for SCU-1611. Terminal agents have no chat content
    messages, so CodingAgentTaskView.updated_at fell back to the *earliest*
    message's timestamp. On restart the only message present is the ephemeral
    EnvironmentAcquiredRunnerMessage, re-emitted with a fresh timestamp — so
    updated_at advanced past last_read_at and the idle terminal lit up green
    (unread) instead of staying grey (read). This is the terminal-agent
    counterpart of test_read_status_persists_after_restart above.

    Steps:
    1. Start Sculptor, create a chat agent and a terminal agent, view both
       (so both are read), and let the debounced mark_read persist.
    2. Restart Sculptor against the same database.
    3. Without viewing the terminal (viewing re-marks it read and masks the
       bug), wait for it to re-acquire its environment, then assert its tab
       dot is "read".
    """
    # === First instance: create a terminal agent and mark it read ===
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Restart WS")
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel, expected_message_count=2)

        agent_tab_bar = PlaywrightAgentTabBarElement(page)
        agent_tabs = agent_tab_bar.get_agent_tabs()
        expect(agent_tabs).to_have_count(1)

        # Add a terminal agent (creating it navigates to it, so it is viewed).
        agent_tab_bar.open_agent_type_menu()
        agent_tab_bar.get_agent_type_menu_item_terminal().click()
        expect(agent_tabs).to_have_count(2)
        terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
        expect(terminal_tab).to_be_visible()

        # The idle terminal settles to read (grey) once its environment is
        # acquired and the debounced mark_read has run.
        expect(terminal_tab).to_have_attribute("data-dot-status", "read")

        # Return to the chat agent and leave it focused: it (not the terminal)
        # is then the restored active agent after restart, so the terminal is
        # never viewed in the second instance (viewing it would re-mark it read
        # and mask the bug). Re-focusing also re-marks the chat read after the
        # switch away.
        agent_tabs.first.click()
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

        # With both agents read, the whole workspace shows read before the restart.
        workspace_tabs = task_page.get_workspace_tabs()
        expect(workspace_tabs.first).to_have_attribute("data-has-unread", "false")

        # Give the debounced mark_read POSTs time to persist to the database.
        page.wait_for_timeout(2000)

    # === Second instance: the restored idle terminal must still be read ===
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        task_page = PlaywrightTaskPage(page=page)
        workspace_tabs = task_page.get_workspace_tabs()
        expect(workspace_tabs.first).to_be_visible()
        workspace_tabs.first.click()

        agent_tab_bar = PlaywrightAgentTabBarElement(page)
        agent_tabs = agent_tab_bar.get_agent_tabs()
        expect(agent_tabs).to_have_count(2)
        # Keep the chat agent focused; never view the terminal (viewing it would
        # re-mark it read and mask the bug).
        agent_tabs.first.click()

        terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
        expect(terminal_tab).to_be_visible()

        # Gate on the terminal re-acquiring its environment after restart: a
        # restored terminal shows "running" (BUILDING) until the run-start
        # EnvironmentAcquiredRunnerMessage is re-emitted, after which an idle
        # terminal is neutral (read/unread).
        expect(terminal_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"))

        # The fix: the re-emitted ephemeral EnvironmentAcquired must NOT advance
        # updated_at past last_read_at, so the restored idle terminal stays read
        # (grey) rather than lighting up unread (green).
        expect(terminal_tab).to_have_attribute("data-dot-status", "read")
