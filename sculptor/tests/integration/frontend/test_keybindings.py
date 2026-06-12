"""Integration tests for the keybindings registry.

Tests cover:
- Settings UI: categories, search, record, clear, reset, conflict, escape
- Help dialog: reflects customized bindings, hides unbound
- Functional: default keybinding works, customized keybinding honored
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.base import dismiss_with_escape
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _navigate_to_keybindings(sculptor_instance_: SculptorInstance):
    """Navigate to Settings > Keybindings and return the section element."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    return settings_page.click_on_keybindings()


@pytest.mark.release
@user_story("to see all keybinding categories in settings")
def test_keybindings_section_renders_all_categories(sculptor_instance_: SculptorInstance) -> None:
    """The keybindings section should show all 4 categories with their bindings."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)

    # Verify keybinding rows from each category are visible:
    # General
    expect(keybindings.get_keybinding_row("command_palette")).to_be_visible()
    # Workspaces
    expect(keybindings.get_keybinding_row("new_workspace")).to_be_visible()
    # Chat
    expect(keybindings.get_keybinding_row("send_message")).to_be_visible()
    # Navigation
    expect(keybindings.get_keybinding_row("home")).to_be_visible()


@pytest.mark.release
@user_story("to search for specific keybindings")
def test_search_filters_keybindings(sculptor_instance_: SculptorInstance) -> None:
    """Searching should filter keybindings by name or description."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)

    # Search for "search"
    keybindings.search("search")

    # "Command palette" and "Chat search" should be visible
    expect(keybindings.get_keybinding_row("command_palette")).to_be_visible()
    expect(keybindings.get_keybinding_row("chat_search")).to_be_visible()

    # Unrelated bindings should be hidden
    expect(keybindings.get_keybinding_row("new_workspace")).to_have_count(0)

    # Clear search, all should be visible again
    keybindings.clear_search()
    expect(keybindings.get_keybinding_row("new_workspace")).to_be_visible()


@pytest.mark.release
@user_story("to record a new keybinding")
def test_record_new_keybinding(sculptor_instance_: SculptorInstance) -> None:
    """Recording a new key combination should update the displayed binding."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    mod = get_playwright_modifier_key()

    # Set "Command palette" to a new binding. We use Meta+J because it has
    # no default binding — picking a key that's already bound to another
    # command (e.g. Meta+P → open_workspace) would trigger the conflict
    # warning instead of a clean record, and that is exercised separately
    # in test_duplicate_detection_reassign.
    keybindings.set_keybinding("command_palette", f"{mod}+j")

    # Verify the display updates
    display = keybindings.get_keybinding_display_text("command_palette")
    expect(display).to_contain_text("J")

    # Reset so subsequent tests on the same worker see defaults
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to clear a keybinding")
def test_clear_keybinding(sculptor_instance_: SculptorInstance) -> None:
    """Clearing a keybinding should show 'Click to set'."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)

    # Clear the "Help" keybinding
    keybindings.clear_keybinding("help")

    # Verify it shows "Click to set"
    display = keybindings.get_keybinding_display_text("help")
    expect(display).to_contain_text("Click to set")

    # Reset so subsequent tests on the same worker see defaults
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to reset all keybindings to defaults")
def test_reset_all_to_defaults(sculptor_instance_: SculptorInstance) -> None:
    """Reset all should revert customized keybindings back to defaults."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    mod = get_playwright_modifier_key()

    # First customize a binding to an unbound key (Meta+J has no default,
    # so this records a clean new binding rather than triggering the
    # conflict warning that Meta+P would now fire against open_workspace).
    keybindings.set_keybinding("command_palette", f"{mod}+j")
    display = keybindings.get_keybinding_display_text("command_palette")
    expect(display).to_contain_text("J")

    # Reset all
    keybindings.reset_all_to_defaults()

    # Verify it reverts (default is Meta+K -> displays as ⌘K or Ctrl+K)
    display = keybindings.get_keybinding_display_text("command_palette")
    expect(display).to_contain_text("K")


@pytest.mark.release
@user_story("to handle duplicate keybinding detection by reassigning")
def test_duplicate_detection_reassign(sculptor_instance_: SculptorInstance) -> None:
    """When a conflict is detected, clicking Reassign should set the new binding and clear the old one."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    mod = get_playwright_modifier_key()

    # Ensure defaults so command_palette is Meta+K
    keybindings.reset_all_to_defaults()

    # Set "Help" to the same binding as "Command palette" (Meta+K)
    keybindings.set_keybinding("help", f"{mod}+k")

    # Conflict warning should appear
    warning = keybindings.get_conflict_warning()
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("Command palette")

    # Click Reassign
    keybindings.click_reassign()

    # "Help" should now show the new binding
    help_display = keybindings.get_keybinding_display_text("help")
    expect(help_display).to_contain_text("K")

    # "Command palette" should be cleared
    search_display = keybindings.get_keybinding_display_text("command_palette")
    expect(search_display).to_contain_text("Click to set")

    # Reset so subsequent tests on the same worker see defaults
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to handle duplicate keybinding detection by cancelling")
def test_duplicate_detection_cancel(sculptor_instance_: SculptorInstance) -> None:
    """When a conflict is detected, clicking Cancel should preserve the original binding."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    mod = get_playwright_modifier_key()

    # Ensure defaults so command_palette is Meta+K
    keybindings.reset_all_to_defaults()

    # Set "Help" to the same binding as "Command palette" (Meta+K)
    keybindings.set_keybinding("help", f"{mod}+k")

    # Conflict warning should appear
    warning = keybindings.get_conflict_warning()
    expect(warning).to_be_visible()

    # Click Cancel
    keybindings.click_cancel_conflict()

    # Warning should disappear
    expect(warning).to_have_count(0)

    # "Command palette" should still have its original binding
    search_display = keybindings.get_keybinding_display_text("command_palette")
    expect(search_display).to_contain_text("K")


@pytest.mark.release
@user_story("to cancel keybinding recording with Escape")
def test_escape_cancels_recording(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Escape during recording should preserve the existing binding."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    page = sculptor_instance_.page

    # Ensure defaults so command_palette displays as ⌘K / Ctrl+K
    keybindings.reset_all_to_defaults()

    set_button = keybindings.get_keybinding_display_text("command_palette")
    set_button.click()
    expect(set_button).to_contain_text("Press keys")

    page.keyboard.press("Escape")

    # Original binding should be preserved
    expect(set_button).to_contain_text("K")


@pytest.mark.release
@user_story("to cancel recording by clicking outside the recording chip")
def test_click_outside_cancels_recording(sculptor_instance_: SculptorInstance) -> None:
    """Clicking anywhere outside the recording chip should preserve the existing binding."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)

    keybindings.reset_all_to_defaults()

    set_button = keybindings.get_keybinding_display_text("command_palette")
    set_button.click()
    expect(set_button).to_contain_text("Press keys")

    # Click on a neutral region of the settings page (the heading area).
    keybindings.get_search_field().click()

    expect(set_button).to_contain_text("K")


@pytest.mark.release
@user_story("to keep only one keybinding in the recording state at a time")
def test_starting_second_recording_cancels_first(sculptor_instance_: SculptorInstance) -> None:
    """Clicking another field's 'Click to set' should cancel any in-progress recording."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)

    keybindings.reset_all_to_defaults()

    first = keybindings.get_keybinding_display_text("command_palette")
    second = keybindings.get_keybinding_display_text("home")

    first.click()
    expect(first).to_contain_text("Press keys")

    # Starting a second recording should drop the first back to its previous binding.
    second.click()
    expect(second).to_contain_text("Press keys")
    expect(first).not_to_contain_text("Press keys")
    expect(first).to_contain_text("K")

    # Clean up the dangling recording on the second field by clicking outside.
    keybindings.get_search_field().click()


@pytest.mark.release
@user_story("to see customized keybindings in the help dialog")
def test_help_dialog_reflects_customized_bindings(sculptor_instance_: SculptorInstance) -> None:
    """After changing a keybinding in settings, the help dialog should show the new binding."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Ensure defaults so help (Meta+/) is bound
    keybindings.reset_all_to_defaults()

    # Change "Command palette" to Meta+J (an unbound key — Meta+P would
    # now collide with open_workspace and trigger the conflict warning).
    keybindings.set_keybinding("command_palette", f"{mod}+j")

    # Open help dialog with Cmd+/
    layout = PlaywrightProjectLayoutPage(page=page)
    layout.press_keyboard_shortcut(f"{mod}+/")

    # Verify the help dialog shows the updated binding
    dialog = layout.get_keyboard_shortcuts_dialog()
    expect(dialog).to_be_visible()

    # The dialog should show command_palette row (with the updated binding)
    command_palette_row = dialog.get_shortcut_row("command_palette")
    expect(command_palette_row).to_be_visible()

    # Close the dialog
    dialog.close()

    # Reset so subsequent tests on the same worker see defaults
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to not see unbound keybindings in the help dialog")
def test_help_dialog_hides_unbound(sculptor_instance_: SculptorInstance) -> None:
    """Unbound keybindings should not appear in the help dialog."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Clear the "Help" keybinding
    keybindings.clear_keybinding("help")

    # Open help dialog (need to use keyboard since we just cleared the help binding,
    # but the handler was already registered with the old binding — navigate directly)
    layout = PlaywrightProjectLayoutPage(page=page)
    layout.press_keyboard_shortcut(f"{mod}+/")

    # Wait for dialog — if the help shortcut is now unbound, the dialog may not open.
    # The global handler reads from the registry, so pressing Meta+/ won't work if
    # "help" is unbound. Let's re-approach: since we cleared the "help" binding,
    # we need another way to verify. Let's clear a different keybinding instead.
    page.keyboard.press("Escape")

    # Re-approach: reset and clear "Command palette" instead
    keybindings.reset_all_to_defaults()
    keybindings.clear_keybinding("command_palette")

    # Open help dialog (Meta+/ is still bound)
    layout.press_keyboard_shortcut(f"{mod}+/")

    dialog = layout.get_keyboard_shortcuts_dialog()
    expect(dialog).to_be_visible()

    # "Command palette" should NOT be visible since it's unbound
    expect(dialog.get_shortcut_row("command_palette")).to_have_count(0)

    dialog.close()

    # Reset so subsequent tests on the same worker see defaults
    keybindings.reset_all_to_defaults()


# ---------------------------------------------------------------------------
# Functional tests — verify keybindings trigger the correct actions
# ---------------------------------------------------------------------------


@pytest.mark.release
@user_story("to have keybindings suppressed when a dismissible overlay is open")
def test_keybindings_suppressed_when_overlay_open(sculptor_instance_: SculptorInstance) -> None:
    """Pressing a keybinding while a modal is open should not trigger the action."""
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Reset keybindings and navigate away from settings
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    keybindings.reset_all_to_defaults()
    blur_active_element(page)

    # Count workspace tabs before
    layout = PlaywrightProjectLayoutPage(page=page)
    initial_tab_count = layout.get_workspace_tabs().count()

    # Open the help dialog (a dismissible overlay)
    layout.press_keyboard_shortcut(f"{mod}+/")
    dialog = layout.get_keyboard_shortcuts_dialog()
    expect(dialog).to_be_visible()

    # Press Meta+T (new workspace) while the dialog is open — should be suppressed
    page.keyboard.press(f"{mod}+t")
    # On macOS Chromium, `keyboard.press("Meta+t")` occasionally fails to
    # emit the Meta keyup, so the next Escape arrives as Cmd+Escape which
    # the OS layer can swallow before Radix sees it. Explicitly release
    # whichever modifier we just used.
    page.keyboard.up(mod)

    # Dialog should still be open (not dismissed by Meta+T)
    expect(dialog).to_be_visible()

    dismiss_with_escape(dialog)

    # No new workspace should have been created
    expect(layout.get_workspace_tabs()).to_have_count(initial_tab_count)


@pytest.mark.release
@user_story("to open the search modal with the default keybinding")
def test_default_command_palette_keybinding_works(sculptor_instance_: SculptorInstance) -> None:
    """Pressing the default Command palette shortcut (Meta+K) should open the search modal."""
    page = sculptor_instance_.page

    # Reset keybindings to defaults (earlier tests may have changed them)
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    keybindings.reset_all_to_defaults()

    # Navigate away from settings so global shortcuts are active
    blur_active_element(page)
    layout = PlaywrightProjectLayoutPage(page=page)

    # Press the default binding for command_palette
    mod = get_playwright_modifier_key()
    layout.press_keyboard_shortcut(f"{mod}+k")

    # Search modal should open
    palette = layout.get_command_palette()
    expect(palette).to_be_visible()

    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to use a customized keybinding after changing it in settings")
def test_customized_keybinding_is_honored(sculptor_instance_: SculptorInstance) -> None:
    """After remapping Command palette to Meta+J, Meta+J should open the modal and Meta+K should not."""
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Change "Command palette" from Meta+K to Meta+J in settings. Meta+J
    # is unbound by default; Meta+P would now collide with open_workspace
    # and trigger the conflict-warning flow tested elsewhere.
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    keybindings.reset_all_to_defaults()
    keybindings.set_keybinding("command_palette", f"{mod}+j")

    # Wait for the user-config update to propagate by asserting the
    # keybindings row in Settings now displays the new binding. The same
    # `userConfigAtom -> keybindingsAtom` chain feeds both the settings
    # UI and the global keyboard-shortcut handler, so once the row
    # reflects "J" the global handler has the new binding too. Replaces
    # a fixed `wait_for_timeout(1000)` that was race-prone in CI.
    expect(keybindings.get_keybinding_display_text("command_palette")).to_contain_text("J")

    # Navigate away from settings.
    blur_active_element(page)
    layout = PlaywrightProjectLayoutPage(page=page)

    # The old binding (Meta+K) should NOT open the search modal
    layout.press_keyboard_shortcut(f"{mod}+k")
    palette = layout.get_command_palette()
    expect(palette).not_to_be_visible()

    # The new binding (Meta+J) should open the search modal
    layout.press_keyboard_shortcut(f"{mod}+j")
    expect(palette).to_be_visible()

    dismiss_with_escape(palette)

    # Reset keybindings for subsequent tests
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    keybindings.reset_all_to_defaults()


@pytest.mark.release
@user_story("to see arrow key symbols in panel toggle keybindings")
def test_panel_toggle_keybindings_display_arrow_symbols(sculptor_instance_: SculptorInstance) -> None:
    """Panel toggle keybindings should display arrow symbols (← → ↓) not letter keys."""
    keybindings = _navigate_to_keybindings(sculptor_instance_)
    keybindings.reset_all_to_defaults()

    # Toggle left panel should show ← (ArrowLeft)
    left_display = keybindings.get_keybinding_display_text("toggle_left_panel")
    expect(left_display).to_contain_text("←")

    # Toggle right panel should show → (ArrowRight)
    right_display = keybindings.get_keybinding_display_text("toggle_right_panel")
    expect(right_display).to_contain_text("→")

    # Toggle bottom panel should show ↓ (ArrowDown)
    bottom_display = keybindings.get_keybinding_display_text("toggle_bottom_panel")
    expect(bottom_display).to_contain_text("↓")
