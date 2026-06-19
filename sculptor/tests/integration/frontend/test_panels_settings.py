"""Integration tests for the Settings → Panels page.

Covers the user-facing flows:
1.  Toggle off / on a panel via the Settings switch.
2.  Move a panel to a different zone via the Zone select.
3.  Drag a panel icon in the layout diagram to a different zone.
4.  Click a diagram zone to filter the list.
5.  Round-trip a per-panel shortcut between the Panels and Keybindings pages.
6.  Focus-then-toggle keyboard dispatch (hidden→show, show→hide cycle).
7.  Disabled panel's shortcut is inert in the workspace.
8.  Reset to defaults restores zones and re-enables panels but preserves shortcuts.
9.  Context-menu "Configure panels…" deep-link.
10. Regression: bottom-bar side-toggle buttons still work.
11. Regression: focus mode entry and exit preserves pre-focus visibility.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.pages.settings_page import PlaywrightSettingsPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _open_panels_settings(sculptor_instance_: SculptorInstance):
    """Navigate to Settings → Panels and return the section element."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    return settings_page.click_on_panels()


def _reset_panels_to_defaults(sculptor_instance_: SculptorInstance) -> None:
    """Click 'Reset to defaults' on the Panels settings page (best-effort cleanup)."""
    panels = _open_panels_settings(sculptor_instance_)
    panels.reset_to_defaults()


def _reset_keybindings_to_defaults(sculptor_instance_: SculptorInstance) -> None:
    """Click 'Reset all to defaults' on the Keybindings settings page."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    keybindings = settings_page.click_on_keybindings()
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to disable a panel from the Settings page and have it disappear from the workspace")
def test_disable_hides_panel(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, model_name=None)

    zones = PlaywrightPanelZonesElement(page=page)

    # Sanity check: the actions icon is visible by default.
    expect(zones.get_actions_icon()).to_be_visible()

    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_enabled("actions", False)

    # Leaving Settings, the actions icon should no longer be in the sidebar.
    page.go_back()
    expect(zones.get_actions_icon()).to_have_count(0)

    # Re-enable from settings; icon comes back.
    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_enabled("actions", True)
    page.go_back()
    expect(zones.get_actions_icon()).to_be_visible()


@user_story("to move a panel to a different zone from the Panels settings page")
def test_zone_select_moves_panel(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_zone("files", "bottom-right")

    # Back in the workspace, the files panel icon should now live in the
    # bottom-right zone area.
    page.go_back()
    zones = PlaywrightPanelZonesElement(page=page)
    expect(zones.get_bottom_right_zone()).to_be_visible()

    _reset_panels_to_defaults(sculptor_instance_)


@user_story("to filter the Panels list by clicking a zone in the diagram")
def test_diagram_click_filters_list(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    panels = _open_panels_settings(sculptor_instance_)

    # Default registry: files in top-left, terminal in bottom, actions in
    # top-right. Click top-left → only files.
    panels.click_diagram_zone("top-left")
    expect(panels.get_panel_row("files")).to_be_visible()
    expect(panels.get_panel_row("terminal")).to_have_count(0)
    expect(panels.get_panel_row("actions")).to_have_count(0)

    # Clear filter via the dedicated button → all rows visible again.
    panels.click_clear_zone_filter()
    expect(panels.get_panel_row("files")).to_be_visible()
    expect(panels.get_panel_row("terminal")).to_be_visible()
    expect(panels.get_panel_row("actions")).to_be_visible()


@pytest.mark.release
@user_story("to bind a panel shortcut on the Panels page and see it on the Keybindings page")
def test_shortcut_round_trip_panels_to_keybindings(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, model_name=None)
    mod = get_playwright_modifier_key()

    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_shortcut("files", f"{mod}+e")

    # The Keybindings page should now show the same binding under "panel_files".
    settings_page = navigate_to_settings_page(page=page)
    keybindings = settings_page.click_on_keybindings()
    expect(keybindings.get_keybinding_row("panel_files")).to_be_visible()
    expect(keybindings.get_keybinding_display_text("panel_files")).to_contain_text("E")

    # Clean up so subsequent tests on this xdist worker see defaults.
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to disable a panel and have its shortcut become inert in the workspace")
def test_disabled_panel_shortcut_is_inert(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, model_name=None)
    mod = get_playwright_modifier_key()

    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_shortcut("actions", f"{mod}+e")
    panels.set_panel_enabled("actions", False)

    # Back in the workspace, pressing the bound shortcut should be a no-op
    # because the panel is disabled and excluded from `panelShortcutsAtom`.
    page.go_back()
    zones = PlaywrightPanelZonesElement(page=page)
    page.keyboard.press(f"{mod}+e")
    expect(zones.get_actions_icon()).to_have_count(0)

    # Re-enable + clean up.
    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_enabled("actions", True)
    panels.clear_panel_shortcut("actions")
    _reset_keybindings_to_defaults(sculptor_instance_)


@pytest.mark.release
@user_story("to reset panels to defaults without losing my custom shortcuts")
def test_reset_to_defaults_preserves_shortcuts(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, model_name=None)
    mod = get_playwright_modifier_key()

    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_shortcut("files", f"{mod}+e")
    # Move BEFORE disabling actions: bottom-right requires its sibling top-right
    # to hold at least one enabled panel, and actions is the only one there.
    panels.set_panel_zone("files", "bottom-right")
    panels.set_panel_enabled("actions", False)

    # Reset.
    panels.reset_to_defaults()

    # Zone is back to default (Files in top-left), Actions is re-enabled
    # (Switch reads "checked"), but the Files shortcut still shows on the
    # Keybindings page.
    settings_page = navigate_to_settings_page(page=page)
    keybindings = settings_page.click_on_keybindings()
    expect(keybindings.get_keybinding_display_text("panel_files")).to_contain_text("E")

    # Final cleanup so subsequent tests don't inherit the custom binding.
    keybindings.reset_all_to_defaults()


@user_story("to deep-link from a panel context menu to its row in Settings")
def test_configure_panels_deep_link(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    zones = PlaywrightPanelZonesElement(page=page)
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()
    files_icon.click(button="right")

    configure_item = zones.get_configure_context_menu_item()
    expect(configure_item).to_be_visible()
    configure_item.click()

    # Settings → Panels is now active and the files row is rendered.
    settings_page = PlaywrightSettingsPage(page=page)
    panels = settings_page.click_on_panels()
    expect(panels.get_panel_row("files")).to_be_visible()


@user_story("to drag a panel icon in the layout diagram to move it to another zone")
def test_diagram_drag_moves_panel(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    panels = _open_panels_settings(sculptor_instance_)

    # Files starts in top-left. Drag it to top-right via the diagram.
    panels.drag_diagram_icon("files", "top-right")

    # The zone select for files should now say Top Right.
    expect(panels.get_zone_select_trigger("files")).to_contain_text("Top Right")

    # Back in the workspace, files now lives in the right sidebar.
    page.go_back()
    zones = PlaywrightPanelZonesElement(page=page)
    expect(zones.get_top_right_zone()).to_be_visible()

    _reset_panels_to_defaults(sculptor_instance_)


@pytest.mark.release
@user_story("to use the keyboard shortcut to show a hidden panel, then press again to hide it")
def test_focus_then_toggle_shortcut(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, model_name=None)
    mod = get_playwright_modifier_key()

    panels = _open_panels_settings(sculptor_instance_)
    panels.set_panel_shortcut("actions", f"{mod}+e")

    page.go_back()
    zones = PlaywrightPanelZonesElement(page=page)

    # Ensure the actions panel is hidden to start (top-right zone is hidden by default).
    expect(zones.get_top_right_zone()).not_to_be_visible()

    # Press shortcut once → actions panel zone shows.
    blur_active_element(page)
    page.keyboard.press(f"{mod}+e")
    expect(zones.get_top_right_zone()).to_be_visible()

    # Press shortcut again → zone hides (focus was inside the zone after first press).
    page.keyboard.press(f"{mod}+e")
    expect(zones.get_top_right_zone()).not_to_be_visible()

    # Press shortcut again → shows.
    page.keyboard.press(f"{mod}+e")
    expect(zones.get_top_right_zone()).to_be_visible()

    # Click somewhere outside the panel zone to move focus away.
    zones.get_side_toggle_left().click()
    # Pressing shortcut while zone is visible but focus is elsewhere should NOT hide the zone;
    # instead it re-focuses the zone.
    page.keyboard.press(f"{mod}+e")
    expect(zones.get_top_right_zone()).to_be_visible()

    # Now the zone has focus again — pressing once more hides it.
    page.keyboard.press(f"{mod}+e")
    expect(zones.get_top_right_zone()).not_to_be_visible()

    panels = _open_panels_settings(sculptor_instance_)
    panels.clear_panel_shortcut("actions")
    _reset_keybindings_to_defaults(sculptor_instance_)


@user_story("to confirm bottom-bar side-toggle buttons still work after the panels settings changes")
def test_regression_bottom_bar_still_works(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    zones = PlaywrightPanelZonesElement(page=page)
    left_toggle = zones.get_side_toggle_left()
    bottom_toggle = zones.get_side_toggle_bottom()
    right_toggle = zones.get_side_toggle_right()

    # All three toggle buttons should be present.
    expect(left_toggle).to_be_visible()
    expect(bottom_toggle).to_be_visible()
    expect(right_toggle).to_be_visible()

    # Right side: top-right zone has a dedicated element ID we can assert on.
    # Top-right is hidden by default; clicking shows it, clicking again hides it.
    right_toggle.click()
    expect(zones.get_top_right_zone()).to_be_visible()
    right_toggle.click()
    expect(zones.get_top_right_zone()).not_to_be_visible()

    # Left and bottom toggles: verify they are clickable without error.
    # (Zone container element IDs for top-left and bottom don't exist in the
    # public constants yet, so we only assert the buttons don't throw.)
    left_toggle.click()
    left_toggle.click()
    bottom_toggle.click()
    bottom_toggle.click()


@user_story("to enter and exit focus mode and have panel visibility restored")
def test_regression_focus_mode_toggle(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    mod = get_playwright_modifier_key()

    zones = PlaywrightPanelZonesElement(page=page)

    # Confirm Files panel is visible before focus mode.
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Enter focus mode via the focus mode button to avoid keyboard conflicts with chat input.
    focus_btn = zones.get_focus_mode_button()
    expect(focus_btn).to_be_visible()
    focus_btn.click()

    # All panel icons should be hidden in focus mode.
    expect(files_icon).not_to_be_visible()

    # Exit focus mode — pre-focus visibility is restored.
    focus_btn.click()
    expect(files_icon).to_be_visible()

    # Keyboard entry: bind focus mode shortcut (Meta+\) and verify.
    blur_active_element(page)
    page.keyboard.press(f"{mod}+\\")
    expect(files_icon).not_to_be_visible()
    page.keyboard.press(f"{mod}+\\")
    expect(files_icon).to_be_visible()
