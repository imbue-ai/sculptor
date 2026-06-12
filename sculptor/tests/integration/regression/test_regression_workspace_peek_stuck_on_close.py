"""Regression test: workspace peek overlay stuck after middle-click closing the last tab.

When the user hovers a workspace tab to open the peek popover, then
middle-clicks the tab to close it (while Home or Settings is open),
the popover must be dismissed.  Previously, the popover stayed visible
permanently because only left-click fired the dismiss handler.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to close a workspace tab via middle-click without the peek popover getting stuck")
def test_workspace_peek_dismissed_on_middle_click_close(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Middle-clicking a workspace tab to close it should dismiss the
    workspace peek popover, even when it's the last workspace tab."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page)

    # Create a workspace so we have a tab to close
    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Done"}`',
        workspace_name="Peek WS",
    )

    # Navigate to Home so the Home tab is open alongside the workspace tab
    navigate_to_home_page(page)

    # Hover over the workspace tab to trigger the peek popover
    workspace_tab = layout.get_workspace_tabs().first
    workspace_tab.hover()

    popover = layout.get_workspace_peek_popover()
    expect(popover).to_be_visible()

    # Middle-click the workspace tab to close it
    workspace_tab.click(button="middle")

    # The popover must be dismissed — it should not remain stuck on screen
    expect(popover).to_be_hidden()
