"""Integration tests for section resizing (SEC-17, SEC-22).

A section's grid border is a focusable ``role=separator`` resize handle driven by the
keyboard (arrow keys step by ~10% of the parent), mirroring the shared-sidebar resize
test. Resizing changes only the section's geometry — it must not change the active
panel or the collapse state of any section. These assertions are kept coarse and
tolerant (direction-of-change), not exact-pixel, to avoid layout-math flakiness.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to resize a section by dragging its border")
def test_resize_right_section_changes_width(sculptor_instance_: SculptorInstance) -> None:
    """Driving the right section's resize handle changes the section's width (SEC-17).

    The right handle grows the section as it moves toward the section (its onResize
    direction is inverted), so ArrowLeft widens it. The width is read from the
    section root's bounding box and only the direction of change is asserted.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Resize Width WS")

    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    section_root = right.get_section()
    expect(section_root).to_be_visible()

    handle = right.get_resize_handle()
    expect(handle).to_be_visible()

    start_box = section_root.bounding_box()
    assert start_box is not None
    start_width = start_box["width"]

    # Grow the right section: ArrowLeft widens it (inverted onResize direction).
    handle.focus()
    for _ in range(3):
        handle.press("ArrowLeft")

    # Poll the rendered width rather than reading a once-evaluated bounding box, so a
    # slow relayout under CI load is tolerated. Only the direction of change is asserted.
    page.wait_for_function(
        """({ testId, startWidth }) => {
            const el = document.querySelector(`[data-testid="${testId}"]`);
            return el && el.getBoundingClientRect().width > startWidth;
        }""",
        arg={"testId": str(ElementIDs.SECTION_RIGHT), "startWidth": start_width},
    )


@user_story("to keep a section's width within sensible bounds while resizing")
def test_resize_clamps_to_a_minimum_width(sculptor_instance_: SculptorInstance) -> None:
    """Shrinking the right section well past its minimum clamps rather than collapsing (SEC-22).

    Repeated shrink steps must leave the section with a positive, non-trivial width
    (the geometry clamps each side to a minimum), not zero.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Resize Clamp WS")

    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    handle = right.get_resize_handle()
    expect(handle).to_be_visible()

    # Shrink the right section well past any minimum: ArrowRight narrows it.
    handle.focus()
    for _ in range(40):
        handle.press("ArrowRight")

    # Poll the rendered width rather than reading a once-evaluated bounding box, so a
    # slow relayout under CI load is tolerated: the section must remain with a clamped
    # (non-zero) width, not zero.
    page.wait_for_function(
        """(testId) => {
            const el = document.querySelector(`[data-testid="${testId}"]`);
            return el && el.getBoundingClientRect().width > 50;
        }""",
        arg=str(ElementIDs.SECTION_RIGHT),
    )
    expect(right.get_header()).to_be_visible()


@user_story("to keep my active panel and layout unchanged when I resize a section")
def test_resize_does_not_change_active_panel_or_collapse(sculptor_instance_: SculptorInstance) -> None:
    """Resizing is pure geometry: it leaves the active panel and collapse state intact (SEC-17)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Resize Pure WS")

    center = PlaywrightWorkspaceSection(page, "center")
    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()

    active_before = center.get_active_tab().get_attribute("data-panel-id")
    assert active_before is not None

    handle = right.get_resize_handle()
    expect(handle).to_be_visible()
    handle.focus()
    for _ in range(3):
        handle.press("ArrowLeft")

    # The center's active panel is unchanged and the right section is still expanded.
    expect(center.get_active_tab()).to_have_attribute("data-panel-id", active_before)
    expect(right.get_header()).to_be_visible()
