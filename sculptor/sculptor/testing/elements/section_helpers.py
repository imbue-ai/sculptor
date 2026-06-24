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
from sculptor.testing.utils import get_playwright_modifier_key

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


# The workspace-section keyboard shortcuts (their default bindings live in the
# keybindings registry). "mod" is the platform primary modifier (Meta on macOS, Control
# elsewhere); the section-cycle bindings use a LITERAL Control regardless of platform.
_TOGGLE_ARROW_BY_SECTION: dict[str, str] = {
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "bottom": "ArrowDown",
}


def press_section_shortcut(page: Page, shortcut: str) -> None:
    """Press a keyboard shortcut and release every modifier afterwards.

    macOS Chromium occasionally fails to emit a modifier keyup after a chord, leaving
    the modifier "held" so the next plain press arrives modified; this releases every
    non-trailing key explicitly (mirrors ``press_keyboard_shortcut`` on the layout page,
    but works against a bare ``Page`` the section tests already hold).
    """
    page.keyboard.press(shortcut)
    for modifier in shortcut.split("+")[:-1]:
        page.keyboard.up(modifier)


def toggle_section_via_hotkey(page: Page, section: str) -> None:
    """Toggle a non-center section's collapse/expand via its keyboard shortcut.

    ``section`` is "left" | "right" | "bottom" (center has no toggle and its hotkey is
    a no-op). Uses the default ``mod+Alt+Arrow*`` bindings.
    """
    arrow = _TOGGLE_ARROW_BY_SECTION[section]
    mod = get_playwright_modifier_key()
    press_section_shortcut(page, f"{mod}+Alt+{arrow}")


def maximize_active_section(page: Page) -> None:
    """Toggle maximize/restore on the active section via ``mod+Shift+m``."""
    mod = get_playwright_modifier_key()
    press_section_shortcut(page, f"{mod}+Shift+m")


def cycle_sections(page: Page, direction: str) -> None:
    """Cycle the active section via the literal ``Control+``` bindings.

    ``direction`` is "next" (``Control+```) or "previous"
    (``Control+Shift+```). These bindings use a literal Control on every platform,
    NOT the platform primary modifier.
    """
    if direction == "next":
        press_section_shortcut(page, "Control+`")
    elif direction == "previous":
        press_section_shortcut(page, "Control+Shift+`")
    else:
        raise ValueError(f"unsupported cycle direction: {direction!r}; expected 'next' or 'previous'")


def cycle_panels(page: Page, direction: str) -> None:
    """Cycle the active panel within the active section via ``mod+Alt+]`` / ``mod+Alt+[``.

    ``direction`` is "next" (``mod+Alt+]``) or "previous" (``mod+Alt+[``).
    """
    mod = get_playwright_modifier_key()
    if direction == "next":
        press_section_shortcut(page, f"{mod}+Alt+]")
    elif direction == "previous":
        press_section_shortcut(page, f"{mod}+Alt+[")
    else:
        raise ValueError(f"unsupported cycle direction: {direction!r}; expected 'next' or 'previous'")
