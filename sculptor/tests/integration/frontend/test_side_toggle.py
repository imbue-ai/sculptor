"""Integration tests for the panel side toggle buttons in the bottom bar.

Tests the three toggle buttons (left, bottom, right) that control grouped
zone visibility from the bottom status bar.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.elements.panels import ensure_right_area_visible
from sculptor.testing.elements.panels import ensure_terminal_visible
from sculptor.testing.elements.terminal import get_add_terminal_button
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to toggle the right sidebar visibility using the bottom bar button")
def test_right_side_toggle_hides_and_shows_panels(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the right side toggle should hide, then restore, the right panel area.

    Steps:
    1. Create a workspace
    2. Ensure the right side is visible (open a panel if needed)
    3. Click the right side toggle button in the bottom bar
    4. Assert the right area is hidden
    5. Click the right side toggle button again
    6. Assert the right area is visible again
    """
    page = sculptor_instance_.page
    panel_zones = PlaywrightPanelZonesElement(page)

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # The right side may or may not have visible panels depending on the
    # default layout.  Toggle a panel on if needed so we have something to
    # hide/show.
    right_area = panel_zones.get_right_area()
    ensure_right_area_visible(page)
    expect(right_area).to_be_visible()

    right_toggle = panel_zones.get_side_toggle_right()
    expect(right_toggle).to_be_visible()
    right_toggle.click()

    expect(right_area).not_to_be_visible()

    right_toggle.click()

    expect(right_area).to_be_visible()


@user_story("to toggle the bottom panel visibility using the bottom bar button")
def test_bottom_toggle_hides_and_shows_terminal(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the bottom toggle should hide, then restore, the bottom panel zone.

    Steps:
    1. Create a workspace
    2. Ensure the terminal panel is visible (open it if needed)
    3. Click the bottom toggle to hide it
    4. Assert the terminal icon is visible but bottom zone is hidden
    5. Click the bottom toggle again to restore
    """
    page = sculptor_instance_.page
    panel_zones = PlaywrightPanelZonesElement(page)

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # The terminal panel may already be open depending on the default layout.
    terminal_icon = panel_zones.get_terminal_icon()
    expect(terminal_icon).to_be_visible()
    ensure_terminal_visible(page)
    add_terminal_button = get_add_terminal_button(page)

    bottom_toggle = panel_zones.get_side_toggle_bottom()
    expect(bottom_toggle).to_be_visible()
    bottom_toggle.click()

    # Terminal icon should still be accessible, but the bottom zone content is gone
    expect(terminal_icon).to_be_visible()
    expect(add_terminal_button).not_to_be_visible()

    bottom_toggle.click()

    expect(add_terminal_button).to_be_visible()
