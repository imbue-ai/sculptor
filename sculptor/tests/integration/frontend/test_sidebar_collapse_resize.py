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
    sidebar_root = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    expect(sidebar_root).to_be_visible()

    sidebar.collapse()

    # The rail is gone and only the expand icon remains.
    expect(sidebar_root).to_be_hidden()
    expect(sidebar.get_expand_icon()).to_be_visible()


@user_story("to reopen the sidebar from its collapsed expand icon")
def test_expand_restores_sidebar(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the expand icon restores the full sidebar rail."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Expand WS")

    sidebar = get_workspace_sidebar(page)
    sidebar_root = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)

    sidebar.collapse()
    expect(sidebar_root).to_be_hidden()

    sidebar.expand()

    # The rail is back and the expand icon is gone.
    expect(sidebar_root).to_be_visible()
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
    sidebar_root = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    expect(sidebar_root).to_be_visible()

    start_box = sidebar_root.bounding_box()
    assert start_box is not None
    start_width = start_box["width"]

    handle = sidebar.get_resize_handle()
    expect(handle).to_be_visible()
    handle.focus()
    for _ in range(3):
        handle.press("ArrowRight")

    grown_box = sidebar_root.bounding_box()
    assert grown_box is not None
    assert grown_box["width"] > start_width, (
        f"Sidebar should widen after ArrowRight: start={start_width:.0f}, grown={grown_box['width']:.0f}"
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
    sidebar_root = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)

    handle = sidebar.get_resize_handle()
    expect(handle).to_be_visible()
    handle.focus()
    # ArrowLeft narrows it; drive it well past the minimum.
    for _ in range(40):
        handle.press("ArrowLeft")

    clamped_box = sidebar_root.bounding_box()
    assert clamped_box is not None
    assert clamped_box["width"] > 100, f"Sidebar must clamp above zero, got {clamped_box['width']:.0f}"
    expect(sidebar_root).to_be_visible()
