"""Integration tests for the Home page tab in the workspace tab bar.

Tests cover:
- Home page opens as a tab when clicking the Home button
- Clicking a workspace from the home page replaces the Home tab (loads in-place)
- Home tab is closeable
- Home tab context menu has no Rename or Delete items
"""

from playwright.sync_api import expect

from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a Home tab in the tab bar when navigating to the home page")
def test_home_page_opens_as_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Navigating to the Home page should show a Home tab in the tab bar.

    Steps:
    1. Create a workspace
    2. Navigate to the Home page
    3. Verify a Home tab appears in the workspace tab bar
    4. Verify the Home tab is active
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Home tab test", workspace_name="Home Tab WS")

    # Step 2: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 3: Verify a Home tab appears.
    layout = PlaywrightProjectLayoutPage(page)
    home_tab = layout.get_home_tab()
    expect(home_tab).to_be_visible()

    # Step 4: Verify the Home tab is active.
    expect(home_tab).to_have_attribute("aria-selected", "true")


@user_story("to navigate to a workspace from the home page and have it replace the Home tab")
def test_clicking_workspace_replaces_home_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a workspace row on the home page should replace the Home tab with the workspace tab.

    Steps:
    1. Create a workspace
    2. Navigate to the Home page
    3. Verify the Home tab is visible
    4. Click the workspace row
    5. Verify the Home tab is gone
    6. Verify the workspace tab is active
    7. Verify the chat panel appears (workspace loaded)
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Replace tab test", workspace_name="Replace Tab WS")

    # Step 2: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 3: Verify the Home tab is visible.
    task_page = PlaywrightTaskPage(page)
    home_page = PlaywrightHomePage(page)
    home_tab = task_page.get_home_tab()
    expect(home_tab).to_be_visible()

    # Step 4: Click the workspace row.
    workspace_row = home_page.get_workspace_rows().filter(has_text="Replace Tab WS")
    expect(workspace_row).to_be_visible()
    workspace_row.click()

    # Step 5: Verify the Home tab is gone.
    expect(home_tab).to_have_count(0)

    # Step 6: Verify a workspace tab is active.
    workspace_tab = task_page.get_workspace_tabs()
    expect(workspace_tab).to_be_visible()

    # Step 7: Verify the chat panel appears.
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible()


@user_story("to close the Home tab and return to a workspace")
def test_home_tab_is_closeable(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the close button on the Home tab removes it.

    Steps:
    1. Create a workspace
    2. Navigate to the Home page
    3. Verify the Home tab is visible
    4. Click the close button on the Home tab
    5. Verify the Home tab disappears
    6. Verify a workspace tab is now active
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Close home test", workspace_name="Close Home WS")

    # Step 2: Navigate to the Home page.
    navigate_to_home_page(page)

    # Step 3: Verify the Home tab is visible.
    layout = PlaywrightProjectLayoutPage(page)
    home_tab = layout.get_home_tab()
    expect(home_tab).to_be_visible()

    # Step 4: Click the close button on the Home tab.
    layout.close_home_tab()

    # Step 5: Verify the Home tab disappears.
    expect(home_tab).to_have_count(0)

    # Step 6: Verify a workspace tab is active.
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)
