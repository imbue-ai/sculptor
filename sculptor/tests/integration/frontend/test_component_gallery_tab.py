"""Integration tests for the Component Gallery pseudo-tab in the workspace tab bar.

Tests cover:
- Component Gallery opens as a tab when clicking the button in Theme Builder
- Component Gallery tab is closeable
- Component Gallery context menu has no Rename or Delete items
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _open_component_gallery_tab(sculptor_instance: SculptorInstance) -> None:
    """Navigate to Theme Builder settings and click the Component Gallery button."""
    page = sculptor_instance.page
    settings_page = navigate_to_settings_page(page=page)
    theme_builder = settings_page.click_on_theme_builder()
    theme_builder.click_component_gallery_button()

    # Wait for the Component Gallery tab to appear before returning.
    layout = PlaywrightProjectLayoutPage(page=page)
    gallery_tab = layout.get_component_gallery_tab()
    expect(gallery_tab).to_be_visible()


@user_story("to open Component Gallery as a tab from Theme Builder settings")
def test_component_gallery_opens_as_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the Component Gallery button in Theme Builder opens a tab in the tab bar.

    Steps:
    1. Create a workspace
    2. Open Theme Builder settings and click Component Gallery button
    3. Verify a Component Gallery tab appears in the workspace tab bar
    4. Verify the Component Gallery tab is active
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Gallery test", workspace_name="Gallery WS")

    _open_component_gallery_tab(sculptor_instance_)

    layout = PlaywrightProjectLayoutPage(page=page)
    gallery_tab = layout.get_component_gallery_tab()
    expect(gallery_tab).to_be_visible()

    expect(gallery_tab).to_have_attribute("aria-selected", "true")


@user_story("to close the Component Gallery tab and return to a workspace")
def test_component_gallery_tab_is_closeable(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the close button on the Component Gallery tab removes it.

    Steps:
    1. Create a workspace
    2. Open Component Gallery tab
    3. Click the close button on the Component Gallery tab
    4. Verify the Component Gallery tab disappears
    5. Verify a workspace tab is now active
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Close gallery test", workspace_name="Close Gallery WS")

    _open_component_gallery_tab(sculptor_instance_)

    layout = PlaywrightProjectLayoutPage(page=page)
    gallery_tab = layout.get_component_gallery_tab()
    expect(gallery_tab).to_be_visible()

    close_button = gallery_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    expect(gallery_tab).to_have_count(0)

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)


@user_story("to verify Component Gallery context menu has no Rename or Delete")
def test_component_gallery_tab_context_menu_no_rename_or_delete(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Right-clicking the Component Gallery tab shows Close items but no Rename or Delete.

    Steps:
    1. Create a workspace and open Component Gallery tab
    2. Right-click the Component Gallery tab
    3. Verify Close is visible
    4. Verify Rename is not present
    5. Verify Delete is not present
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Menu test", workspace_name="Menu Gallery WS")
    _open_component_gallery_tab(sculptor_instance_)

    layout = PlaywrightProjectLayoutPage(page=page)
    tab_bar = PlaywrightAgentTabBarElement(page)
    gallery_tab = layout.get_component_gallery_tab()
    expect(gallery_tab).to_be_visible()
    tab_bar.open_context_menu(gallery_tab)

    close_item = tab_bar.get_context_menu_close_item()
    expect(close_item).to_be_visible()

    rename_item = tab_bar.get_context_menu_rename_item()
    expect(rename_item).to_have_count(0)

    delete_item = tab_bar.get_context_menu_delete_item()
    expect(delete_item).to_have_count(0)
