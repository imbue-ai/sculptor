"""Section-interaction helpers for the workspace section/panel shell (Phase 4).

These drive the real UI the way a user does — clicking section controls, pressing the
keyboard shortcuts, and dragging panel tabs through the dnd-kit KeyboardSensor — rather
than seeding layout state, so the tests exercise the same code paths as production.

The drag helper is the load-bearing one: panel drag-and-drop is driven via the
KeyboardSensor (Task 4.1), which Playwright can drive faithfully (focus the tab's drag
handle, Space to pick up, one arrow per section to move, Space to drop) where a
synthetic pointer drag cannot. The provider's directional coordinate getter makes a
single arrow press jump to the adjacent section.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs

_ARROW_BY_DIRECTION: dict[str, str] = {
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "up": "ArrowUp",
    "down": "ArrowDown",
}

# A drag steps at most this many sections in one direction (left↔center↔right is the
# widest run); the loop stops as soon as the target lights up as the drop target.
_MAX_DRAG_STEPS = 4


def _section_drop_target(page: Page, sub_section: str):  # noqa: ANN202 - playwright Locator
    """The element carrying the live drop-target flag for a sub-section.

    Matches whichever is mounted: the expanded section body (PanelSection) or the
    collapsed section's drop rail — both carry ``data-drop-target-subsection``. The
    CSS-attribute scoping stays inside this helper to honour the integration-test
    css-locator ratchet.
    """
    return page.locator(f'[data-drop-target-subsection="{sub_section}"]')


def drag_panel_to_section(
    page: Page, panel_id: str, source_sub_section: str, target_sub_section: str, direction: str
) -> None:
    """Drag a panel tab into another section via the KeyboardSensor.

    ``direction`` is the arrow to step toward the target ("left"/"right"/"up"/"down");
    the helper presses it until the target section reports ``data-drop-active`` (the
    isDropTargetAtom slice), then drops. Verifies the panel tab lands in the target.

    The KeyboardSensor picks up on Space but attaches its arrow/end keydown listener on
    a deferred tick AND marks the source section as the initial drop target, so the
    helper waits for that source highlight before pressing arrows — otherwise the first
    arrow is dispatched before the listener is live and is silently dropped.
    """
    handle = page.get_by_test_id(f"{ElementIDs.PANEL_TAB_DRAG_HANDLE}-{panel_id}")
    expect(handle).to_be_visible()
    handle.focus()
    page.keyboard.press("Space")  # pick up
    expect(_section_drop_target(page, source_sub_section)).to_have_attribute("data-drop-active", "true")

    arrow = _ARROW_BY_DIRECTION[direction]
    target = _section_drop_target(page, target_sub_section)
    for _step in range(_MAX_DRAG_STEPS):
        page.keyboard.press(arrow)
        try:
            expect(target).to_have_attribute("data-drop-active", "true", timeout=1_000)
            break
        except AssertionError:
            continue
    page.keyboard.press("Space")  # drop

    landed = page.get_by_test_id(f"{ElementIDs.SECTION_HEADER}-{target_sub_section}").get_by_test_id(
        f"{ElementIDs.PANEL_TAB}-{panel_id}"
    )
    expect(landed).to_be_visible()
