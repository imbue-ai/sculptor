"""Integration tests for fast mode persistence across navigation and reload.

Verifies that:
- Fast mode persists when sending a message and navigating to a different agent
- Fast mode persists when toggled WITHOUT sending a message and switching agents
- Disabling fast mode WITHOUT sending persists when switching agents
- Fast mode persists across a page reload (localStorage-backed)
- Fast mode persists across a send on a non-fast model (no cross-model contamination)
- Fast mode respects the user's defaultFastMode setting on a task's first visit
- Fast mode does not flicker off during the send round-trip
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_2_MODEL_NAME
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.user_config import enable_default_fast_mode
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _expect_fast_mode_active(chat_panel: PlaywrightChatPanelElement) -> None:
    """Assert fast mode toggle shows as active."""
    toggle = chat_panel.get_fast_mode_toggle()
    expect(toggle).to_have_attribute("data-active", "true")


def _expect_fast_mode_inactive(chat_panel: PlaywrightChatPanelElement) -> None:
    """Assert fast mode toggle shows as inactive."""
    toggle = chat_panel.get_fast_mode_toggle()
    expect(toggle).to_have_attribute("data-active", "false")


@user_story("to have fast mode stay enabled when switching between agents")
def test_fast_mode_persists_after_sending_message_and_switching_agents(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Toggle fast mode on, send a message, navigate to another agent, then come back.

    Fast mode should still be active on the original agent when navigating back.
    """
    page = sculptor_instance_.page

    # Create first agent in a workspace
    task_page = start_task_and_wait_for_ready(page, prompt="First agent", workspace_name="Fast Mode WS")
    chat_panel = task_page.get_chat_panel()
    agent_tab_bar = task_page.get_agent_tab_bar()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Enable fast mode
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_active(chat_panel)

    # Send a follow-up message with fast mode enabled
    send_chat_message(chat_panel, "Follow up message")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Add a second agent to the workspace
    agent_tab_bar.get_add_agent_button().click()

    # Wait for second agent tab to appear
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # We're now on the second agent — fast mode should be off by default
    expect(chat_panel.get_chat_input()).to_be_visible()
    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "false")

    # Navigate back to the first agent
    agent_tabs.first.click()

    # Fast mode should still be active on the first agent
    _expect_fast_mode_active(chat_panel)


@user_story("to have fast mode stay enabled when toggled without sending a message")
def test_fast_mode_persists_without_sending_message(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Toggle fast mode on WITHOUT sending a message, switch agents, come back.

    Fast mode should still be active on the original agent.
    """
    page = sculptor_instance_.page

    # Create first agent in a workspace
    task_page = start_task_and_wait_for_ready(page, prompt="First agent", workspace_name="FM No Send WS")
    chat_panel = task_page.get_chat_panel()
    agent_tab_bar = task_page.get_agent_tab_bar()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Enable fast mode — do NOT send a message
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_active(chat_panel)

    # Add a second agent to the workspace
    agent_tab_bar.get_add_agent_button().click()

    # Wait for second agent tab to appear
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # We're now on the second agent — fast mode should be off by default
    expect(chat_panel.get_chat_input()).to_be_visible()
    expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "false")

    # Navigate back to the first agent
    agent_tabs.first.click()

    # Fast mode should still be active on the first agent
    _expect_fast_mode_active(chat_panel)


@user_story("to have fast mode stay disabled when toggled off without sending a message")
def test_fast_mode_disable_persists_without_sending_message(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Enable fast mode, send a message (persisting it), toggle off WITHOUT sending, switch agents, come back.

    Fast mode should remain off on the original agent — the unsent toggle-off must not be lost.
    """
    page = sculptor_instance_.page

    # Create first agent in a workspace
    task_page = start_task_and_wait_for_ready(page, prompt="First agent", workspace_name="FM Disable WS")
    chat_panel = task_page.get_chat_panel()
    agent_tab_bar = task_page.get_agent_tab_bar()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Enable fast mode and send a message to persist it
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_active(chat_panel)
    send_chat_message(chat_panel, "Persist fast mode on")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Now disable fast mode — do NOT send a message
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_inactive(chat_panel)

    # Add a second agent to the workspace
    agent_tab_bar.get_add_agent_button().click()

    # Wait for second agent tab to appear
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Navigate back to the first agent
    agent_tabs.first.click()

    # Fast mode should still be OFF — the unsent toggle-off must persist
    _expect_fast_mode_inactive(chat_panel)


@user_story("to have fast mode stay enabled after a page reload")
def test_fast_mode_survives_page_reload(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Toggle fast mode on, reload the page, fast mode should still be active.

    The in-memory draft atom is wiped on reload; localStorage-backed state
    survives. This test fails if the toggle state lives only in memory.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Reload FM WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Enable fast mode — do NOT send a message
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_active(chat_panel)

    # Full SPA teardown to reset in-memory Jotai atoms while preserving
    # localStorage — simulates an Electron relaunch after sleep. Navigate
    # back to this task's URL afterwards via its hash.
    current_hash = page.url.split("#", 1)[1] if "#" in page.url else "/"
    full_spa_reload(page, target_hash=f"#{current_hash}")
    expect(chat_panel).to_be_visible()

    # Fast mode should still be active after the reload
    _expect_fast_mode_active(chat_panel)


@user_story("to have my fast mode preference preserved after sending on a non-fast model")
def test_fast_mode_survives_cross_model_send(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Toggle fast mode on, switch to a non-fast model, send, switch back.

    The send on the non-fast model must not wipe the user's stored
    preference for the fast-capable model. Uses Fake Claude 2 (configured
    with supportsFastMode=false in modelCapabilities.ts) so the send stays
    deterministic.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Cross-model FM WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Toggle fast mode ON on Fake Claude (fast-capable)
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_active(chat_panel)

    # Switch to Fake Claude 2 (non-fast) — toggle must unmount
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_2_MODEL_NAME)
    expect(chat_panel.get_fast_mode_toggle()).not_to_be_visible()

    # Send a message on the non-fast model
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "non-fast send"}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Switch back to Fake Claude (fast-capable) — toggle must remount and
    # still be ON (stored preference is independent of the backend
    # message-derived task.fastMode).
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    _expect_fast_mode_active(chat_panel)


@user_story("to see fast mode on by default when I've set defaultFastMode=true")
def test_fast_mode_respects_default_on_first_visit(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Set defaultFastMode=true, create a new agent, toggle starts on.

    With a single source of truth and a lazy-init-from-user-default
    policy, the toggle must be on from the first render for a brand-new
    task — no config-load race, no off-then-on flicker.
    """
    page = sculptor_instance_.page

    # Set defaultFastMode=true (reloads the page as part of applying the config)
    enable_default_fast_mode(page)

    # Create a brand-new agent with that default in place
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Default FM WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Toggle must be on — respects the user's default
    _expect_fast_mode_active(chat_panel)


@user_story("to never see fast mode flicker off during a send")
def test_fast_mode_stays_on_across_send(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Toggle fast mode on, send a message, assert the toggle stays on.

    Regression guard for the post-send clear that used to wipe the draft
    atom immediately after the HTTP resolved, falling back to stale
    task/default state until the WebSocket update landed.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="No Flicker WS",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Enable fast mode
    toggle = chat_panel.get_fast_mode_toggle()
    toggle.click()
    _expect_fast_mode_active(chat_panel)

    # Send a message — this triggers the HTTP round-trip + WebSocket push
    # that historically flickered the toggle off.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "no flicker"}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Toggle must still be active after the round-trip resolves.
    _expect_fast_mode_active(chat_panel)
