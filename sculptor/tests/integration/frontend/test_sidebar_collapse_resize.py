"""Integration tests for collapsing and resizing the workspace sidebar.

The sidebar collapses to a single top-left expand icon (the rail disappears) and
expands back from it; its right border is a focusable ``role=separator`` resize
handle driven by the keyboard (arrow keys step by ~10% of the parent), mirroring
the section resize handles. Width changes are asserted coarsely
(direction-of-change / clamp), not exact-pixel, to avoid layout-math flakiness.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to collapse the sidebar down to a single expand icon")
def test_collapse_hides_sidebar_and_shows_expand_icon(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the collapse toggle hides the sidebar rail and reveals the expand icon."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Collapse WS")

    sidebar = get_workspace_sidebar(page)
    expect(sidebar).to_be_visible()

    sidebar.collapse()

    # The rail is gone and only the expand icon remains.
    expect(sidebar).to_be_hidden()
    expect(sidebar.get_expand_icon()).to_be_visible()


@user_story("to reopen the sidebar from its collapsed expand icon")
def test_expand_restores_sidebar(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the expand icon restores the full sidebar rail."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Expand WS")

    sidebar = get_workspace_sidebar(page)

    sidebar.collapse()
    expect(sidebar).to_be_hidden()

    sidebar.expand()

    # The rail is back and the expand icon is gone.
    expect(sidebar).to_be_visible()
    expect(sidebar.get_expand_icon()).to_be_hidden()


@user_story("to resize the sidebar by dragging its border")
def test_resize_handle_widens_sidebar(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Driving the sidebar's resize handle changes its width.

    The handle is an x-axis separator with direction=1, so ArrowRight widens it.
    Only the direction of change is asserted.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Sidebar Resize WS")

    sidebar = get_workspace_sidebar(page)
    expect(sidebar).to_be_visible()

    start_box = sidebar.bounding_box()
    assert start_box is not None
    start_width = start_box["width"]

    handle = sidebar.get_resize_handle()
    expect(handle).to_be_visible()
    handle.focus()
    for _ in range(3):
        handle.press("ArrowRight")

    # Poll the rendered width rather than reading a once-evaluated bounding box, so a
    # slow relayout under CI load is tolerated. Only the direction of change is asserted.
    page.wait_for_function(
        """({ testId, startWidth }) => {
            const el = document.querySelector(`[data-testid="${testId}"]`);
            return el && el.getBoundingClientRect().width > startWidth;
        }""",
        arg={"testId": str(ElementIDs.WORKSPACE_SIDEBAR), "startWidth": start_width},
    )


@user_story("to keep the sidebar width within sensible bounds while resizing")
def test_resize_clamps_to_a_minimum_width(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Shrinking the sidebar well past its minimum clamps rather than vanishing.

    Repeated narrow steps must leave the sidebar with a positive, non-trivial width
    (it clamps at a minimum of 180px), not zero.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Sidebar Clamp WS")

    sidebar = get_workspace_sidebar(page)

    handle = sidebar.get_resize_handle()
    expect(handle).to_be_visible()
    handle.focus()
    # ArrowLeft narrows it; drive it well past the minimum.
    for _ in range(40):
        handle.press("ArrowLeft")

    # Poll the rendered width rather than reading a once-evaluated bounding box, so a
    # slow relayout under CI load is tolerated: the sidebar must remain with a clamped
    # (non-zero) width, not zero.
    page.wait_for_function(
        """(testId) => {
            const el = document.querySelector(`[data-testid="${testId}"]`);
            return el && el.getBoundingClientRect().width > 100;
        }""",
        arg=str(ElementIDs.WORKSPACE_SIDEBAR),
    )
    expect(sidebar).to_be_visible()
