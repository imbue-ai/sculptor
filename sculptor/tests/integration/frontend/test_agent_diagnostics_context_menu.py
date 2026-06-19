"""Integration tests for agent tab Diagnostics context menu.

Tests cover:
- Diagnostics copy items are disabled when no session exists
- Copy session id and transcript path copy correct values to clipboard
- Copy agent name (top-level menu) and Copy agent id (Diagnostics) copy correct values
"""

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.clipboard import reset_intercepted_clipboard
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see diagnostics items disabled when no session exists")
def test_agent_diagnostics_disabled_without_session(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Diagnostics copy items are disabled for an agent that has not run yet.

    Steps:
    1. Create a workspace with an agent that has completed
    2. Add a second agent (which has no session yet)
    3. Right-click the new agent tab and open the Diagnostics sub-menu
    4. Verify Copy session id and Copy transcript path items are disabled
    """
    page = sculptor_instance_.page
    tab_bar = PlaywrightAgentTabBarElement(page)

    # Step 1: Create a workspace with a completed agent.
    start_task_and_wait_for_ready(page, prompt="Diagnostics test", workspace_name="Diag Disabled WS")

    # Step 2: Add a second agent that has no session.
    tab_bar.get_add_agent_button().click()
    agent_tabs = tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Step 3: Right-click the new (second) agent tab, open Diagnostics.
    tab_bar.open_diagnostics_submenu(agent_tabs.nth(1))

    # Step 4: Verify both items are disabled (Radix uses data-disabled attribute).
    copy_session_id = tab_bar.get_copy_session_id_item()
    expect(copy_session_id).to_be_visible()
    expect(copy_session_id).to_have_attribute("data-disabled", "")

    copy_transcript_path = tab_bar.get_copy_transcript_path_item()
    expect(copy_transcript_path).to_be_visible()
    expect(copy_transcript_path).to_have_attribute("data-disabled", "")

    copy_sculptor_transcript = tab_bar.get_copy_sculptor_transcript_item()
    expect(copy_sculptor_transcript).to_be_visible()
    expect(copy_sculptor_transcript).to_have_attribute("data-disabled", "")


@user_story("to copy diagnostics info from the agent tab context menu")
def test_agent_diagnostics_copy_session_id_and_transcript_path(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking diagnostics copy items copies the correct values to the clipboard.

    Steps:
    1. Create a workspace with an agent that has completed
    2. Install clipboard interceptor
    3. Copy session id and verify a non-empty value was copied
    4. Copy transcript path and verify a .jsonl path was copied
    5. Copy Sculptor transcript path and verify a TRANSCRIPT.jsonl path was copied
    """
    page = sculptor_instance_.page
    tab_bar = PlaywrightAgentTabBarElement(page)

    # Step 1: Create a workspace with an agent that has completed.
    start_task_and_wait_for_ready(page, prompt="Diagnostics copy test", workspace_name="Diag Copy WS")

    # Step 2: Install clipboard interceptor.
    install_clipboard_interceptor(page)

    # Step 3: Copy session id.
    agent_tabs = tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)
    tab_bar.open_diagnostics_submenu(agent_tabs.first)

    copy_session_id = tab_bar.get_copy_session_id_item()
    expect(copy_session_id).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_session_id.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    session_id = read_intercepted_clipboard(page)
    assert session_id is not None, "Expected session ID to be copied to clipboard"
    assert len(session_id) > 0, "Expected non-empty session ID"

    # Step 4: Copy transcript path.
    tab_bar.open_diagnostics_submenu(agent_tabs.first)

    copy_transcript_path = tab_bar.get_copy_transcript_path_item()
    expect(copy_transcript_path).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_transcript_path.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    transcript_path = read_intercepted_clipboard(page)
    assert transcript_path is not None, "Expected transcript path to be copied to clipboard"
    assert transcript_path.endswith(".jsonl"), f"Expected .jsonl path, got: {transcript_path}"

    # Step 5: Copy Sculptor transcript path.
    tab_bar.open_diagnostics_submenu(agent_tabs.first)

    copy_sculptor_transcript = tab_bar.get_copy_sculptor_transcript_item()
    expect(copy_sculptor_transcript).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_sculptor_transcript.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    sculptor_transcript_path = read_intercepted_clipboard(page)
    assert sculptor_transcript_path is not None, "Expected Sculptor transcript path to be copied to clipboard"
    assert sculptor_transcript_path.endswith("transcript.jsonl"), (
        f"Expected transcript.jsonl path, got: {sculptor_transcript_path}"
    )


@user_story("to copy the agent name and id from the agent tab context menu")
def test_agent_context_menu_copy_name_and_id(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Copy agent name (top-level menu) and Copy agent id (Diagnostics) copy the right values.

    Unlike the session/transcript items, these don't depend on a running
    session — they are available as soon as the agent exists.

    Steps:
    1. Create a workspace with an agent
    2. Install clipboard interceptor
    3. Copy agent name from the top-level context menu and verify it matches the tab name
    4. Copy agent id from the Diagnostics sub-menu and verify a non-empty value
    """
    page = sculptor_instance_.page
    tab_bar = PlaywrightAgentTabBarElement(page)

    # Step 1: Create a workspace with an agent.
    start_task_and_wait_for_ready(page, prompt="Diagnostics name/id test", workspace_name="Diag Name Id WS")

    # Step 2: Install clipboard interceptor.
    install_clipboard_interceptor(page)
    agent_tabs = tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Step 3: Copy agent name from the top-level context menu.
    tab_bar.open_context_menu(agent_tabs.first)
    copy_agent_name = tab_bar.get_copy_agent_name_item()
    expect(copy_agent_name).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_agent_name.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    agent_name = read_intercepted_clipboard(page)
    assert agent_name, "Expected agent name to be copied to clipboard"
    # The copied name is the agent's display name, which the tab shows.
    expect(agent_tabs.first).to_contain_text(agent_name)

    # Step 4: Copy agent id from the Diagnostics sub-menu.
    tab_bar.open_diagnostics_submenu(agent_tabs.first)
    copy_agent_id = tab_bar.get_copy_agent_id_item()
    expect(copy_agent_id).to_be_visible()
    reset_intercepted_clipboard(page)
    copy_agent_id.click()

    page.wait_for_function("() => window.__clipboardWritten !== null")
    agent_id = read_intercepted_clipboard(page)
    assert agent_id, "Expected agent id to be copied to clipboard"
