"""Integration tests for the closed workspaces dropdown feature.

These tests verify:
- The "Closed N" pill appears/disappears based on closed workspace count
- The dropdown opens and displays closed workspace rows
- Reopening a workspace from the dropdown restores its tab
- Deleting a workspace from the dropdown removes it permanently
- The "Open all" button reopens all closed workspaces
"""

from playwright.sync_api import expect

from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a pill showing the count of closed workspaces")
def test_pill_visibility_toggles_with_closed_workspace_count(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify the pill appears when workspaces are closed and updates its count."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="WS One")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="WS Two")
    start_task_and_wait_for_ready(page, prompt="Agent 3", workspace_name="WS Three")

    pill = layout.get_closed_workspaces_pill()
    expect(pill).not_to_be_visible()

    # Close the first workspace tab
    layout.close_workspace_tab(workspace_tab_index=0)

    expect(pill).to_be_visible()
    expect(pill).to_contain_text("1")

    # Close the second workspace tab (keep the third open so we don't
    # redirect to the Open Workspace page, which hides the pill)
    layout.close_workspace_tab(workspace_tab_index=0)

    expect(pill).to_contain_text("2")


@user_story("to see closed workspaces in a dropdown")
def test_dropdown_opens_and_shows_closed_workspace_rows(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify the dropdown opens with workspace rows when the pill is clicked."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="My Closed WS")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="My Open WS")

    layout.close_workspace_tab(workspace_tab_index=0)

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    pill.click()

    dropdown_element = layout.get_closed_workspaces_dropdown()
    expect(dropdown_element).to_be_visible()

    rows = dropdown_element.get_rows()
    expect(rows).to_have_count(1)

    # Click outside the dropdown to close it (click on the top bar)
    topbar = layout.get_topbar()
    topbar.click(position={"x": 5, "y": 5})
    expect(dropdown_element).not_to_be_visible()


@user_story("to reopen a closed workspace from the dropdown")
def test_reopen_workspace_from_dropdown(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify clicking a row in the dropdown reopens the workspace as a tab."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Reopen WS")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="Stay Open WS")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    layout.close_workspace_tab(workspace_tab_index=0)
    expect(workspace_tabs).to_have_count(1)

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    pill.click()

    dropdown_element = layout.get_closed_workspaces_dropdown()
    row = dropdown_element.get_rows()
    expect(row).to_be_visible()
    row.click()

    # Workspace tab should reappear and pill should disappear
    expect(workspace_tabs).to_have_count(2)
    expect(pill).not_to_be_visible()


@user_story("to delete a closed workspace from the dropdown")
def test_delete_workspace_from_dropdown(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify deleting a workspace from the dropdown removes it permanently."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Delete WS")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="Keep WS")

    layout.close_workspace_tab(workspace_tab_index=0)

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    pill.click()

    # Wait for the dropdown's open animation to settle before hovering.  A
    # row that's technically "visible" mid-transform has a moving hit target,
    # and hover() retries on instability — that's been timing out on slow CI.
    dropdown_element = layout.get_closed_workspaces_dropdown()
    expect(dropdown_element).to_be_visible()
    row = dropdown_element.get_rows()
    expect(row).to_have_count(1)
    row.hover()

    delete_button = dropdown_element.get_delete_button()
    expect(delete_button).to_be_visible()
    delete_button.click()

    # Confirmation dialog should appear
    confirm_dialog = dropdown_element.get_delete_confirmation_dialog()
    expect(confirm_dialog).to_be_visible()

    confirm_button = dropdown_element.get_delete_confirmation_confirm_button()
    confirm_button.click()

    # Dialog should close and pill should disappear (no more closed workspaces)
    expect(confirm_dialog).to_be_hidden()
    expect(pill).not_to_be_visible()


@user_story("to see the closed workspaces pill on the new workspace modal")
def test_pill_visible_on_new_workspace_modal(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify the pill remains visible when opening the new workspace modal."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="WS One")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="WS Two")

    # Close one workspace so the pill appears
    layout.close_workspace_tab(workspace_tab_index=0)

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("1")

    # Open the new workspace modal
    layout.get_add_workspace_button().click()

    # Pill should still be visible on the new workspace modal
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("1")


@user_story("to reopen all closed workspaces at once")
def test_open_all_reopens_all_closed_workspaces(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Verify the 'Open all' button reopens all closed workspaces."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="WS Alpha")
    start_task_and_wait_for_ready(page, prompt="Agent 2", workspace_name="WS Beta")
    start_task_and_wait_for_ready(page, prompt="Agent 3", workspace_name="WS Gamma")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(3)

    # Close two workspace tabs (keep one open so we don't redirect
    # to the Open Workspace page, which hides the pill)
    layout.close_workspace_tab(workspace_tab_index=0)
    # Let the first close settle on the backend before issuing the second,
    # so we don't race WebSocket updates that could resurrect the first tab.
    expect(workspace_tabs).to_have_count(2)
    layout.close_workspace_tab(workspace_tab_index=0)
    expect(workspace_tabs).to_have_count(1)

    pill = layout.get_closed_workspaces_pill()
    expect(pill).to_contain_text("2")
    pill.click()

    dropdown_element = layout.get_closed_workspaces_dropdown()
    expect(dropdown_element).to_be_visible()

    rows = dropdown_element.get_rows()
    expect(rows).to_have_count(2)

    open_all_button = dropdown_element.get_open_all_button()
    expect(open_all_button).to_be_visible()
    open_all_button.click()

    # Both closed workspace tabs should reappear and pill should disappear
    expect(workspace_tabs).to_have_count(3)
    expect(pill).not_to_be_visible()
    expect(dropdown_element).not_to_be_visible()
