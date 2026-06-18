"""Integration tests for model-specific capability gating in the chat input.

Verifies that:
- The fast mode toggle is only visible when Claude Opus 4.6 is selected
- The fast mode draft state is preserved when switching away from Opus 4.6 and back
- The model selector is isolated per agent (changing one agent's model doesn't bleed to others)
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Long display names as they appear in the model selector dropdown (ModelSelectOptions uses getModelLongName).
_OPUS_48_1M_MODEL_NAME = "Claude 4.8 Opus (1M)"
_OPUS_48_MODEL_NAME = "Claude 4.8 Opus"
_OPUS_46_MODEL_NAME = "Claude 4.6 Opus (1M)"
_SONNET_MODEL_NAME = "Claude 4.6 Sonnet"


@user_story("to only see the fast mode toggle when Opus 4.6 is selected")
def test_fast_mode_toggle_gated_by_model(sculptor_instance_: SculptorInstance) -> None:
    """Fast mode toggle should only be present in the chat toolbar for Opus 4.6.

    Steps:
    1. Start with Fake Claude (which supports fast mode for testing) — toggle visible.
    2. Switch to Sonnet — toggle must disappear.
    3. Switch to Opus 4.6 — toggle must reappear.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Fast Mode Gating WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Fake Claude supports fast mode — toggle should be visible.
    expect(chat_panel.get_fast_mode_toggle()).to_be_visible()

    # Switch to Sonnet — fast mode is not supported, toggle must disappear.
    select_model_by_name(chat_panel, _SONNET_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).not_to_be_visible()

    # Switch to Opus 4.6 — fast mode is supported, toggle must reappear.
    select_model_by_name(chat_panel, _OPUS_46_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).to_be_visible()


@user_story("to see the fast mode toggle when Opus 4.8 is selected")
def test_fast_mode_toggle_visible_for_opus_48(sculptor_instance_: SculptorInstance) -> None:
    """Fast mode toggle must be present for Opus 4.8, just like 4.7 and 4.6 (SCU-1541).

    Opus 4.8 reuses the generic CLAUDE_4_OPUS / CLAUDE_4_OPUS_200K enum values
    (only the display label in modelConstants.ts was bumped to "Claude 4.8
    Opus"); the matching entries in modelCapabilities.ts were left at
    supportsFastMode: false. As a result the toggle was hidden for 4.8 even
    though it appears for 4.7/4.6.

    Steps:
    1. Start with Fake Claude (supports fast mode) — toggle visible.
    2. Switch to Sonnet — toggle must disappear (clean baseline).
    3. Switch to Opus 4.8 (1M) — toggle must reappear.
    4. Switch to Opus 4.8 (200K) — toggle must remain visible.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Opus 4.8 Fast Mode WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Fake Claude supports fast mode — toggle should be visible.
    expect(chat_panel.get_fast_mode_toggle()).to_be_visible()

    # Switch to Sonnet — fast mode is not supported, toggle must disappear.
    select_model_by_name(chat_panel, _SONNET_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).not_to_be_visible()

    # Switch to Opus 4.8 (1M) — fast mode is supported, toggle must reappear.
    select_model_by_name(chat_panel, _OPUS_48_1M_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).to_be_visible()

    # Switch to Opus 4.8 (200K) — fast mode is supported, toggle must stay visible.
    select_model_by_name(chat_panel, _OPUS_48_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).to_be_visible()


@user_story("to have my fast mode preference remembered when switching back to Opus 4.6")
def test_fast_mode_draft_survives_model_switch(sculptor_instance_: SculptorInstance) -> None:
    """Fast mode draft state should be preserved when the user switches away from Opus 4.6 and back.

    Steps:
    1. Switch to Opus 4.6 — fast mode toggle appears (inactive by default).
    2. Enable fast mode.
    3. Switch to Sonnet — toggle disappears.
    4. Switch back to Opus 4.6 — toggle reappears and should still be active.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Fast Mode Draft WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Switch to Opus 4.6 and verify the toggle is present but inactive.
    select_model_by_name(chat_panel, _OPUS_46_MODEL_NAME)
    toggle = chat_panel.get_fast_mode_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("data-active", "false")

    # Enable fast mode.
    toggle.click()
    expect(toggle).to_have_attribute("data-active", "true")

    # Switch to Sonnet — toggle should no longer be visible.
    select_model_by_name(chat_panel, _SONNET_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).not_to_be_visible()

    # Switch back to Opus 4.6 — the draft should be preserved: toggle is active.
    select_model_by_name(chat_panel, _OPUS_46_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "true")


@user_story("to have an independent model selector for each agent in a workspace")
def test_model_selector_is_isolated_per_agent(sculptor_instance_: SculptorInstance) -> None:
    """Model selector changes on one agent must not bleed into other agents.

    Root cause: localModel in ChatInput is useState (component-local). Because
    ChatInput is never unmounted when switching agents, the useState value from
    the previous agent persists when taskModel is falsy (new agent, no messages).

    Steps:
    1. Create Agent 1 — starts with "Fake Claude" model.
    2. Change Agent 1's model to "Fake Claude 2" WITHOUT sending a message.
    3. Add Agent 2 via the "+" button.
    4. Agent 2 should show its default model ("Opus"), NOT Agent 1's choice.
    5. Navigate back to Agent 1 — should still show "Fake Claude 2".
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "model isolation"}`',
        workspace_name="Model Isolation WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Agent 1 should initially show "Fake Claude".
    model_selector = chat_panel.get_model_selector()
    expect(model_selector).to_contain_text("Fake Claude")

    # Change Agent 1's model to "Fake Claude 2" WITHOUT sending a message.
    select_model_by_name(chat_panel, "Fake Claude 2")
    expect(model_selector).to_contain_text("Fake Claude 2")

    # Add Agent 2 via the "+" button.
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Wait for Agent 2's chat input to appear.
    task_page_2 = PlaywrightTaskPage(page=page)
    chat_panel_2 = task_page_2.get_chat_panel()
    expect(chat_panel_2.get_chat_input()).to_be_visible()
    agent_2_model_selector = chat_panel_2.get_model_selector()

    # Agent 2 must NOT show Agent 1's "Fake Claude 2" override.
    # In integration tests the backend creates new tasks with Fake Claude as the default model,
    # so the selector should show "Fake Claude", not "Fake Claude 2".
    expect(agent_2_model_selector).not_to_contain_text("Fake Claude 2")

    # Navigate back to Agent 1 — its model choice must be preserved.
    agent_tabs.first.click()
    expect(model_selector).to_contain_text("Fake Claude 2")
