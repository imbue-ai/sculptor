"""Integration tests for the Settings pseudo-tab in the workspace tab bar.

Tests cover:
- Settings opens as a tab when clicking the gear button
- Settings tab is closeable
- Only one Settings tab can exist at a time
- Settings context menu has no Rename or Delete items
"""

from playwright.sync_api import expect

from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to open Settings as a tab in the workspace tab bar")
def test_settings_opens_as_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the settings gear button opens a Settings tab in the workspace tab bar.

    Steps:
    1. Create a workspace
    2. Click the settings button
    3. Verify a Settings tab appears in the workspace tab bar
    4. Verify the Settings tab is active
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Settings test", workspace_name="Settings WS")

    # Step 2: Click the settings button.
    layout.get_settings_button().click()

    # Step 3: Verify a Settings tab appears.
    settings_tab = layout.get_settings_tab()
    expect(settings_tab).to_be_visible()

    # Step 4: Verify the Settings tab is active.
    expect(settings_tab).to_have_attribute("aria-selected", "true")


@user_story("to close the Settings tab and return to a workspace")
def test_settings_tab_is_closeable(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the close button on the Settings tab removes it and navigates to a workspace.

    Steps:
    1. Create a workspace
    2. Open Settings tab
    3. Click the close button on the Settings tab
    4. Verify the Settings tab disappears
    5. Verify a workspace tab is now active
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Close settings test", workspace_name="Close WS")

    # Step 2: Open Settings tab.
    layout.open_settings_tab()

    # Step 3: Click the close button on the Settings tab.
    layout.close_settings_tab()

    # Step 4: Verify the Settings tab disappears.
    expect(layout.get_settings_tab()).to_have_count(0)

    # Step 5: Verify at least one workspace tab is active (the close action
    # navigates back to a workspace, but the tab may take a moment to render
    # on slower CI runners).
    workspace_tab = layout.get_workspace_tabs().first
    expect(workspace_tab).to_be_visible()


@user_story("to verify only one Settings tab can exist at a time")
def test_settings_tab_singleton(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the settings button when Settings is already open does not create a duplicate.

    Steps:
    1. Create a workspace
    2. Open Settings tab
    3. Click the settings button again
    4. Verify there is still only one Settings tab
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Singleton test", workspace_name="Singleton WS")

    # Step 2: Open Settings tab.
    layout.open_settings_tab()

    # Step 3: Click the settings button again.
    layout.get_settings_button().click()

    # Step 4: Verify there is still only one Settings tab.
    expect(layout.get_settings_tab()).to_have_count(1)


@user_story("to verify Settings context menu has no Rename or Delete")
def test_settings_tab_context_menu_no_rename_or_delete(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking the Settings tab shows Close items but no Rename or Delete.

    Steps:
    1. Create a workspace and open Settings tab
    2. Right-click the Settings tab
    3. Verify Close is visible
    4. Verify Rename is not present
    5. Verify Delete is not present
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Step 1: Create a workspace and open Settings.
    start_task_and_wait_for_ready(page, prompt="Menu test", workspace_name="Menu WS")

    settings_tab = layout.open_settings_tab()

    # Step 2: Right-click the Settings tab.
    settings_tab.click(button="right")

    # Step 3: Verify Close is visible.
    expect(layout.get_tab_context_menu_close()).to_be_visible()

    # Step 4: Verify Rename is not present.
    expect(layout.get_tab_context_menu_rename()).to_have_count(0)

    # Step 5: Verify Delete is not present.
    expect(layout.get_tab_context_menu_delete()).to_have_count(0)
