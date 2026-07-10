"""Integration tests for the mobile WorkspaceDrawer.

The drawer is the mobile navigation surface (the desktop sidebar is suppressed
below 768px): Home / Settings nav, repo-grouped workspace rows with long-press
rename/delete, and a "New workspace" button that opens the shared modal.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.mobile_workspace import enter_mobile_workspace
from sculptor.testing.elements.mobile_workspace import get_delete_confirm_button
from sculptor.testing.elements.mobile_workspace import get_inline_rename_input
from sculptor.testing.elements.mobile_workspace import get_mobile_home_header
from sculptor.testing.elements.mobile_workspace import get_mobile_settings_header
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

pytestmark = pytest.mark.mobile


@user_story("to get to Home from a workspace on mobile")
def test_mobile_drawer_navigates_to_home(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    drawer = shell.open_drawer()
    drawer.get_home_link().click()

    expect(get_mobile_home_header(page)).to_be_visible()


@user_story("to get to Settings from a workspace on mobile")
def test_mobile_drawer_navigates_to_settings(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    drawer = shell.open_drawer()
    drawer.get_settings_link().click()

    expect(get_mobile_settings_header(page)).to_be_visible()


@user_story("to switch between workspaces from the mobile drawer")
def test_mobile_drawer_switches_workspace(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    # Two workspaces so the drawer has one to switch away to; the second is current.
    start_task_and_wait_for_ready(sculptor_page=page)
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    url_before = page.url
    drawer = shell.open_drawer()
    drawer.get_other_workspace_row().click()

    # The drawer closes and the shell re-mounts for the other workspace's agent.
    drawer.expect_closed()
    expect(shell.root()).to_be_visible()
    expect(page).not_to_have_url(url_before)


@user_story("to create a new workspace from the mobile drawer")
def test_mobile_drawer_new_workspace_opens_shared_modal(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    drawer = shell.open_drawer()
    drawer.get_new_workspace_button().click()

    # It opens the same NewWorkspaceModal every desktop entry point uses.
    dialog = PlaywrightNewWorkspaceDialog(page)
    expect(dialog.get_dialog()).to_be_visible()


@user_story("to rename a workspace from the mobile drawer")
def test_mobile_drawer_renames_workspace(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    drawer = shell.open_drawer()
    # Rename the current workspace so the header (which shows the current
    # workspace's name) reflects the change.
    drawer.long_press_workspace_row(drawer.get_current_workspace_row())
    drawer.get_rename_action().click()

    rename_input = get_inline_rename_input(page)
    expect(rename_input).to_be_visible()
    rename_input.fill("Renamed Mobile Workspace")
    rename_input.press("Enter")

    expect(rename_input).to_have_count(0)
    expect(shell.get_header()).to_contain_text("Renamed Mobile Workspace")


@user_story("to delete a workspace from the mobile drawer")
def test_mobile_drawer_deletes_workspace(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    # Two workspaces; we delete the non-current one so the current view isn't stranded.
    start_task_and_wait_for_ready(sculptor_page=page)
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    drawer = shell.open_drawer()
    rows = drawer.get_workspace_rows()
    # Each test starts from a clean instance (_pre_test clears all workspaces), so
    # exactly the two workspaces created above are listed. Assert the absolute
    # counts (auto-waiting) rather than a `.count()` snapshot, which can race the
    # drawer's rows rendering.
    expect(rows).to_have_count(2)

    drawer.long_press_workspace_row(drawer.get_other_workspace_row())
    drawer.get_delete_action().click()
    get_delete_confirm_button(page).click()

    expect(rows).to_have_count(1)
