"""Panel layout helpers for integration tests.

Provides idempotent functions to ensure specific panels are visible or hidden,
regardless of the default layout. Tests that need a particular panel state
should call these helpers rather than inlining visibility checks.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs


def get_add_terminal_button(page: Page) -> Locator:
    """Return the add-terminal toggle button locator.

    Visible only when the bottom (terminal) panel is open; tests assert on
    this to confirm the terminal is showing.
    """
    return page.get_by_test_id(ElementIDs.ADD_TERMINAL_BUTTON)


def close_bottom_panel(page: Page) -> None:
    """Close the bottom panel (terminal) if it is currently open.

    This is a no-op if the terminal is already closed. Useful for scroll
    tests that need maximum chat height.
    """
    terminal_button = page.get_by_test_id(ElementIDs.ADD_TERMINAL_BUTTON)
    if terminal_button.is_visible():
        bottom_toggle = page.get_by_test_id(ElementIDs.SIDE_TOGGLE_BOTTOM)
        bottom_toggle.click()


def ensure_right_area_visible(page: Page) -> None:
    """Ensure the right panel area is visible, opening it if needed.

    Clicks the actions panel icon to show the right side when it's collapsed.
    This is a no-op if the right area is already visible.
    """
    right_area = page.get_by_test_id(ElementIDs.PANEL_RIGHT_AREA)
    if not right_area.is_visible():
        actions_icon = page.get_by_test_id(ElementIDs.PANEL_ICON_ACTIONS)
        actions_icon.click()


def ensure_terminal_visible(page: Page) -> None:
    """Ensure the terminal panel is visible, opening it if needed.

    This is a no-op if the terminal is already visible.
    """
    add_terminal_button = page.get_by_test_id(ElementIDs.ADD_TERMINAL_BUTTON)
    if not add_terminal_button.is_visible():
        bottom_toggle = page.get_by_test_id(ElementIDs.SIDE_TOGGLE_BOTTOM)
        bottom_toggle.click()
