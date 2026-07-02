"""Integration tests for navigating to Settings from the sidebar.

Settings is no longer a closeable pseudo-tab in a workspace tab strip; it is a
route reached from the sidebar's Settings link, and navigating back to a
workspace row leaves it. This rebuilds ``test_settings_tab`` against the sidebar:
the tab-model specifics (closeable / singleton / no-rename context menu) are
dropped along with the tab strip.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to open Settings from the sidebar Settings link")
def test_settings_opens_from_sidebar_link(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the sidebar Settings link navigates to the Settings page.

    Steps:
    1. Create a workspace
    2. Click the sidebar Settings link
    3. Verify the Settings page renders
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Settings test", workspace_name="Settings WS")

    settings_link = sidebar.get_settings_link()
    expect(settings_link).to_be_visible()
    settings_link.click()

    expect(layout.get_settings_page_locator()).to_be_visible()


@user_story("to return to a workspace from Settings via the sidebar")
def test_navigate_from_settings_back_to_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Navigating to a workspace row from Settings leaves the Settings page.

    Steps:
    1. Create a workspace
    2. Open Settings from the sidebar link
    3. Click the workspace row in the sidebar
    4. Verify the Settings page is gone and the workspace chat renders
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)
    layout = PlaywrightProjectLayoutPage(page=page)
    task_page = PlaywrightTaskPage(page)

    start_task_and_wait_for_ready(page, prompt="Back to workspace", workspace_name="Return WS")

    sidebar.get_settings_link().click()
    expect(layout.get_settings_page_locator()).to_be_visible()

    navigate_to_workspace(page, "Return WS")

    expect(layout.get_settings_page_locator()).to_be_hidden()
    expect(task_page.get_chat_panel()).to_be_visible()
