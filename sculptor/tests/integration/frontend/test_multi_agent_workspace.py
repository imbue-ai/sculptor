"""Integration tests for multi-agent workspace functionality with workspace tabs UI.

These tests verify:
- Adding a second agent to an existing workspace via the agent tab "+" button
- Agent tabs correctly reflecting the number of agents in a workspace
- Workspace tabs isolating agents per workspace
- Workspace cleanup when the last agent is deleted
- Workspace survival when one agent is deleted from a multi-agent workspace
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to run multiple agents in the same workspace")
def test_create_second_agent_in_existing_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Create a workspace with one agent, then add a second agent via the "+" button.

    Verifies that clicking ADD_AGENT_BUTTON creates a new agent tab and that
    two agent tabs are visible in the workspace.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # Create first agent in a new workspace
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Multi Agent WS")

    # Verify one agent tab exists
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Click the "+" button in the agent tabs bar to add a second agent
    agent_tab_bar.add_agent()

    # Wait for the second agent tab to appear
    expect(agent_tabs).to_have_count(2)

    # Verify the chat panel is visible for the new agent
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible()


@user_story("to see which agents share a workspace")
def test_multiple_agent_tabs_shown_for_shared_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Create a workspace and add a second agent. Verify 2 agent tabs exist.

    The number of agent tabs indicates workspace sharing.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # Create first agent in a new workspace
    start_task_and_wait_for_ready(page, prompt="First agent task", workspace_name="Shared WS")

    # Add a second agent to the same workspace
    agent_tab_bar.add_agent()

    # Verify 2 agent tabs are visible
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)


@user_story("to see which agents share a workspace")
def test_single_agent_shows_one_agent_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Create a workspace with a single agent. Verify exactly 1 agent tab."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # Create one agent in a new workspace
    start_task_and_wait_for_ready(page, prompt="Only agent in workspace", workspace_name="Solo WS")

    # Verify exactly one agent tab
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Verify exactly one workspace tab
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(1)


@user_story("to see my agents organized by workspace")
def test_workspaces_have_isolated_agent_tabs(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Create two workspaces and verify agent tabs are isolated per workspace.

    Creates workspace A with 2 agents and workspace B with 1 agent.
    Navigating between workspace tabs should show the correct number
    of agent tabs for each workspace.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # Create workspace A with first agent
    start_task_and_wait_for_ready(page, prompt="Agent A1", workspace_name="Workspace A")

    # Add a second agent to workspace A
    agent_tab_bar.add_agent()

    # Verify workspace A has 2 agent tabs
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Create workspace B with one agent (this navigates to the Add Workspace page
    # and creates a new workspace)
    start_task_and_wait_for_ready(page, prompt="Agent B1", workspace_name="Workspace B")

    # Verify workspace B has 1 agent tab
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Verify there are now 2 workspace tabs
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(2)

    # Navigate back to workspace A by clicking its sidebar row
    navigate_to_workspace(page, "Workspace A")

    # Verify workspace A still has 2 agent tabs
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Navigate to workspace B by clicking its sidebar row
    navigate_to_workspace(page, "Workspace B")

    # Verify workspace B still has 1 agent tab
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)


@pytest.mark.skip(reason="Workspace auto-deletion when last agent deleted was removed (15ec747c1c3)")
@user_story("to have empty workspaces cleaned up automatically")
def test_workspace_deleted_when_last_agent_deleted(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting the last agent in a workspace removes the workspace tab.

    Creates a workspace with one agent, deletes the agent via the tab
    context menu, and verifies the workspace tab is removed and the
    workspace directory is cleaned up from disk.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # Create a workspace with one agent
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Deletable WS")

    # Verify workspace row and agent tab exist
    workspace_rows = get_workspace_sidebar(page).get_workspace_rows()
    expect(workspace_rows).to_have_count(1)
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Snapshot workspace directories on disk before deletion (filter out MRU tracking files)
    workspaces_dir = sculptor_instance_.sculptor_folder / "workspaces"
    workspace_dirs_before = {p for p in workspaces_dir.iterdir() if p.is_dir()} if workspaces_dir.exists() else set()
    assert len(workspace_dirs_before) > 0, "Expected at least one workspace directory after agent creation"

    # Delete the agent via the close button
    agent_tabs.first.click()
    close_button = agent_tab_bar.get_tab_close_button(agent_tabs.first)
    close_button.click()

    # Confirm the deletion
    confirm_button = agent_tab_bar.get_delete_confirmation_confirm_button()
    expect(confirm_button).to_be_visible()
    confirm_button.click()

    # Wait for the deletion dialog to close
    expect(agent_tab_bar.get_delete_confirmation_dialog()).to_be_hidden()

    # Workspace tab should be removed (last agent was deleted)
    expect(workspace_rows).to_have_count(0)

    # Verify workspace directories have been cleaned up from disk
    workspace_dirs_after = {p for p in workspaces_dir.iterdir() if p.is_dir()} if workspaces_dir.exists() else set()
    deleted_dirs = workspace_dirs_before - workspace_dirs_after
    assert len(deleted_dirs) > 0, (
        f"Expected at least one workspace directory to be deleted. "
        f"Before: {workspace_dirs_before}, After: {workspace_dirs_after}"
    )


@user_story("to keep workspaces alive while agents still use them")
def test_workspace_survives_when_other_agents_remain(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting one agent from a multi-agent workspace keeps the workspace alive.

    Creates two agents in a workspace, deletes one, and verifies:
    - The workspace tab still exists
    - The workspace directory is intact on disk
    - The remaining agent is still operational (can send and receive messages)
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()
    workspaces_dir = sculptor_instance_.sculptor_folder / "workspaces"

    # Snapshot directories before creating our workspace (shared instance may have others)
    dirs_before_creation = {p for p in workspaces_dir.iterdir() if p.is_dir()} if workspaces_dir.exists() else set()

    # Create a workspace with first agent
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Surviving WS")

    # Add a second agent to the same workspace
    agent_tab_bar.add_agent()

    # Wait for 2 agent tabs
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Identify workspace directories created by this test
    dirs_after_creation = {p for p in workspaces_dir.iterdir() if p.is_dir()}
    new_dirs = dirs_after_creation - dirs_before_creation
    assert len(new_dirs) >= 1, f"Expected at least one new workspace directory, found: {new_dirs}"

    # Delete the second agent (the currently active one) via close button
    agent_tabs.last.click()
    close_button = agent_tab_bar.get_tab_close_button(agent_tabs.last)
    close_button.click()

    # Confirm the deletion
    confirm_button = agent_tab_bar.get_delete_confirmation_confirm_button()
    expect(confirm_button).to_be_visible()
    confirm_button.click()

    # Wait for the deletion dialog to close
    expect(agent_tab_bar.get_delete_confirmation_dialog()).to_be_hidden()

    # Verify only 1 agent tab remains
    expect(agent_tabs).to_have_count(1)

    # Workspace directories should still be intact on disk
    for ws_dir in new_dirs:
        assert ws_dir.is_dir(), f"Workspace directory {ws_dir} should still exist"

    # Verify the remaining agent is operational by navigating to it and sending a message
    agent_tabs.first.click()
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible()

    send_chat_message(chat_panel, "Are you still there?")
    # 2 user messages (initial prompt + follow-up) + 2 assistant responses
    wait_for_completed_message_count(chat_panel, expected_message_count=4)


@user_story("to see agent tabs numbered starting from 1 even after deleting earlier agents")
def test_agent_tab_reuses_lowest_available_number(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting an auto-named agent and adding a new one should reuse the lowest number.

    The first agent created via the Add Workspace form is auto-named "Claude 1"
    (even when a prompt is provided, the backend auto-assigns "Agent N" names).

    Steps:
    1. Create a workspace — first agent is auto-named "Claude 1"
    2. Click "+" twice to create "Claude 2" and "Claude 3"
    3. Delete "Claude 2"
    4. Click "+" — the new agent should be "Claude 2", not "Claude 4"
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # Create a workspace — the first agent is auto-named "Claude 1".
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Reuse WS")

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)
    expect(agent_tabs.first).to_have_text("Claude 1")

    # Add two more agents via the "+" button — they get "Claude 2" and "Claude 3".
    agent_tab_bar.add_agent()
    expect(agent_tabs).to_have_count(2)
    expect(agent_tabs.nth(1)).to_have_text("Claude 2")

    agent_tab_bar.add_agent()
    expect(agent_tabs).to_have_count(3)
    expect(agent_tabs.nth(2)).to_have_text("Claude 3")

    # Delete "Claude 2". On slow CI the close+confirm flow occasionally loses
    # the click (Radix AlertDialog.Action auto-closes the dialog before
    # onConfirm fires), so target Agent 2 by text and retry the UI flow
    # until the tab actually disappears.
    for _attempt in range(3):
        tab2 = agent_tab_bar.get_agent_tab_by_name("Claude 2").first
        if not tab2.is_visible():
            break  # already gone — a previous attempt succeeded
        tab2.click()
        close_button = agent_tab_bar.get_tab_close_button(tab2)
        expect(close_button).to_be_visible()
        close_button.click()
        confirm_button = agent_tab_bar.get_delete_confirmation_confirm_button()
        expect(confirm_button).to_be_visible()
        expect(confirm_button).to_be_enabled()
        confirm_button.click()
        expect(agent_tab_bar.get_delete_confirmation_dialog()).to_be_hidden()
        try:
            expect(agent_tab_bar.get_agent_tab_by_name("Claude 2")).to_have_count(0)
            break
        except AssertionError:
            continue
    else:
        expect(agent_tab_bar.get_agent_tab_by_name("Claude 2")).to_have_count(0)
    expect(agent_tabs).to_have_count(2)

    # The UI removes the tab optimistically, but the backend's "lowest
    # available number" query for the next add needs to see the deletion
    # committed — on slow CI the add request can race the delete commit and
    # return Agent 4 instead of reusing Agent 2. Give the backend more
    # breathing room than the UI-only round-trip would imply.
    page.wait_for_timeout(3_000)

    # Add another agent — should reuse number 2, not increment to 4.
    agent_tab_bar.add_agent()
    expect(agent_tabs).to_have_count(3)
    expect(agent_tabs.nth(2)).to_have_text("Claude 2")


@pytest.mark.skip(
    reason="Existing workspace dropdown removed in workspace tabs migration; workspaces are always visible as tabs"
)
@user_story("to choose from available workspaces when creating an agent")
def test_existing_workspace_dropdown_shows_active_workspaces(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Test that the existing workspace dropdown only shows active workspaces.

    Skipped because the workspace dropdown was removed in the workspace tabs
    migration. Workspaces are always visible as tabs in the top bar.
    """
