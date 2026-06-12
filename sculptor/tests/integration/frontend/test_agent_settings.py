"""Integration test for the Agent settings tab.

Verifies that:
- The Agent tab exists with model, fast mode, and effort level controls
- Defaults flow through to new agents
- Adding a second agent picks up the configured default, not the first agent's override
- Effort level persists per-agent and syncs when switching workspaces
- Effort level persists when changed without sending a message and switching agents
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to configure agent defaults and have them apply to new agents across workspaces")
def test_agent_settings_persist_and_apply_to_new_agents(sculptor_instance_: SculptorInstance) -> None:
    """End-to-end test: configure agent defaults and confirm they apply to new agents.

    Steps:
    1. Open Agent settings tab, verify all three controls are visible
    2. Enable default fast mode and change effort level to High
    3. Create a workspace — verify the agent picks up the configured defaults
    4. Override fast mode on agent 1, then add agent 2 via "+" — verify agent 2 gets
       the configured default (fast mode on), not agent 1's manual override
    """
    page = sculptor_instance_.page

    # -- Step 1: Verify Agent settings tab and all controls --
    settings_page = navigate_to_settings_page(page=page)
    agent_section = settings_page.click_on_agent()

    expect(agent_section.get_model_select()).to_be_visible()
    expect(agent_section.get_fast_mode_toggle()).to_be_visible()
    expect(agent_section.get_effort_level_select()).to_be_visible()

    # -- Step 2: Change defaults --
    # Enable fast mode
    agent_section.get_fast_mode_toggle().click()
    expect(settings_page.get_toast()).to_be_visible()

    # Change effort level to High
    agent_section.select_effort_level("High")
    expect(settings_page.get_toast()).to_be_visible()

    # -- Step 3: Create a workspace — defaults should be applied --
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "hello from agent 1"}`',
        workspace_name="Agent Defaults WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "true")
    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "high")

    # -- Step 4: Override fast mode on agent 1, add agent 2 --
    # Manually disable fast mode on agent 1
    chat_panel.get_fast_mode_toggle().click()
    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "false")

    # Send a message to persist the override
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "still agent 1"}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # After sending, fast mode should STILL be off — the default must not override the explicit choice
    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "false")

    # Add a second agent via the "+" button
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tab_bar.get_agent_tabs()).to_have_count(2)

    # Agent 2 should pick up the configured default (fast mode ON),
    # NOT inherit agent 1's manual override (fast mode OFF)
    expect(chat_panel.get_chat_input()).to_be_visible()
    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "true")

    # -- Cleanup: reset settings to defaults so other shared-instance tests are unaffected --
    settings_page = navigate_to_settings_page(page=page)
    agent_section = settings_page.click_on_agent()

    # Disable fast mode (toggle it back off)
    agent_section.get_fast_mode_toggle().click()
    expect(settings_page.get_toast()).to_be_visible()

    # Reset effort level to the default (Extra High)
    agent_section.select_effort_level("Extra High")
    expect(settings_page.get_toast()).to_be_visible()


@user_story("to have effort level persist when changed without sending a message")
def test_effort_level_persists_without_sending_message(sculptor_instance_: SculptorInstance) -> None:
    """Change effort level WITHOUT sending a message, switch agents, come back.

    Effort level should still reflect the unsent change on the original agent.
    """
    page = sculptor_instance_.page

    # Create first agent in a workspace
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "effort no send"}`',
        workspace_name="Effort No Send WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Verify default effort is Extra High
    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "xhigh")

    # Change effort to High via the chat input selector — do NOT send a message
    chat_panel.select_effort("High")
    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "high")

    # Add a second agent to the workspace
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tab_bar.get_agent_tabs()).to_have_count(2)

    # Second agent should show default effort (Extra High)
    expect(chat_panel.get_chat_input()).to_be_visible()
    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "xhigh")

    # Navigate back to the first agent
    agent_tab_bar.get_agent_tabs().first.click()

    # Effort level should still be High on the first agent
    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "high")


@user_story("to have effort level persist per-agent when switching workspaces")
def test_effort_level_persists_across_workspace_switches(sculptor_instance_: SculptorInstance) -> None:
    """Effort level should sync per-agent when switching between workspaces.

    Steps:
    1. Create workspace 1, change effort to High, send a message to persist it
    2. Create workspace 2 — effort should show the default (Extra High)
    3. Switch back to workspace 1 — effort should show High (the last-used value)
    """
    page = sculptor_instance_.page

    # -- Step 1: Create workspace 1 and change effort to High --
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ws1 agent"}`',
        workspace_name="Effort WS 1",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "xhigh")

    # Change effort to High via the chat input selector
    chat_panel.select_effort("High")
    expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "high")

    # Send a message to persist the effort choice
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "ws1 high effort"}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # -- Step 2: Create workspace 2 — effort should be the default (Extra High) --
    task_page_2 = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ws2 agent"}`',
        workspace_name="Effort WS 2",
    )
    chat_panel_2 = task_page_2.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_2, expected_message_count=2)

    expect(chat_panel_2.get_effort_selector()).to_have_attribute("data-value", "xhigh")

    # -- Step 3: Switch back to workspace 1 — effort should show High --
    task_page_2.get_workspace_tabs().first.click()

    # Wait for the chat panel of workspace 1 to appear
    chat_panel_ws1 = task_page.get_chat_panel()
    expect(chat_panel_ws1).to_be_visible()

    expect(chat_panel_ws1.get_effort_selector()).to_have_attribute("data-value", "high")
