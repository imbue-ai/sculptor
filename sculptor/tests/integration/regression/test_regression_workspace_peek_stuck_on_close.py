"""Regression test: the workspace peek popover dismisses on a middle-click, not only a left-click.

When the user hovers a sidebar workspace row to open the peek popover, then
middle-clicks the row, the popover must be dismissed rather than staying stuck
on screen.  Middle-click fires the DOM "auxclick" event instead of "click", so
the overlay's dismiss listener handles both; a listener bound to "click" alone
would leave the popover visible after a middle-click.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to have the workspace peek popover dismiss when I middle-click a sidebar row")
def test_workspace_peek_dismissed_on_middle_click_close(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Middle-clicking a hovered workspace's sidebar row dismisses the workspace
    peek popover.  The row itself performs no action on middle-click; the
    popover's auxclick listener is what closes it."""
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page)

    # Create a workspace so we have a sidebar row to hover and middle-click
    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Done"}`',
        workspace_name="Peek WS",
    )

    # Drive the sidebar from Home so the hover and middle-click target only the
    # sidebar row and the peek popover, not the workspace's own page.
    navigate_to_home_page(page)

    # Hover over the workspace's sidebar row to trigger the peek popover
    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    workspace_row.hover()

    popover = layout.get_workspace_peek_popover()
    expect(popover).to_be_visible()

    # Middle-click the workspace row.  The row itself does nothing on middle-click;
    # this fires the peek popover's auxclick dismiss listener.
    workspace_row.click(button="middle")

    # The popover must be dismissed — it should not remain stuck on screen
    expect(popover).to_be_hidden()
