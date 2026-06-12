"""Integration tests for the Settings page functionality."""

import pytest
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.testing.elements.base import dismiss_with_escape
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@pytest.mark.release
def test_env_vars_section_shows_setup_instructions(sculptor_instance_: SculptorInstance) -> None:
    """Test that the Environment Variables settings section shows setup instructions."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    env_vars_section = settings_page.click_on_env_vars()
    expect(env_vars_section.get_setup_instructions()).to_be_visible()


@pytest.mark.release
def test_env_vars_override_toggle_exists(sculptor_instance_: SculptorInstance) -> None:
    """Test that the override toggle is visible and starts unchecked (default False)."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    env_vars_section = settings_page.click_on_env_vars()
    toggle = env_vars_section.get_override_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).not_to_be_checked()


@pytest.mark.release
def test_env_vars_override_toggle_saves_setting(sculptor_instance_: SculptorInstance) -> None:
    """Test that clicking the override toggle saves the setting and shows a success toast."""
    sculptor_config_path_ = sculptor_instance_.sculptor_folder / "internal" / "config.toml"
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    env_vars_section = settings_page.click_on_env_vars()
    toggle = env_vars_section.get_override_toggle()
    toggle.click()

    toast = settings_page.get_toast()
    expect(toast).to_be_visible()

    config = load_config(sculptor_config_path_)
    assert config.env_var_override_enabled is True


@pytest.mark.release
def test_env_vars_loaded_names_shows_no_vars_without_env_file(sculptor_instance_: SculptorInstance) -> None:
    """Test that the loaded names list shows 'No variables loaded' when no workspace or .env exists."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    env_vars_section = settings_page.click_on_env_vars()
    expect(env_vars_section.get_no_variables_message()).to_be_visible()


@pytest.mark.release
def test_keybinding_settings_command_palette_shortcut(sculptor_instance_: SculptorInstance):
    """Test that the command palette keybinding works with default and custom values."""
    mod_key = get_playwright_modifier_key()
    page = sculptor_instance_.page

    # Navigate to a workspace page so keyboard shortcuts are available
    page.wait_for_load_state("networkidle")

    # Test default keybinding (Cmd+K / Ctrl+K) works
    layout = PlaywrightProjectLayoutPage(page=page)
    palette = layout.open_command_palette_with_keyboard()
    dismiss_with_escape(palette)

    # Navigate to settings and change the keybinding
    settings_page = navigate_to_settings_page(page=page)
    keybindings = settings_page.click_on_keybindings()

    # Set a new keybinding (Cmd+Shift+G / Ctrl+Shift+G) — Cmd+Shift+F is the
    # default for chat_search, so we pick a free combo to avoid the conflict
    # warning.
    keybindings.set_keybinding("command_palette", f"{mod_key}+Shift+g")

    # Wait for toast to confirm the change was saved
    toast = settings_page.get_toast()
    expect(toast).to_be_visible()

    # Test that old keybinding no longer works
    settings_page.press_keyboard_shortcut(f"{mod_key}+k")
    expect(palette).not_to_be_visible()

    # Test new keybinding works
    settings_page.press_keyboard_shortcut(f"{mod_key}+Shift+g")
    expect(palette).to_be_visible()
    dismiss_with_escape(palette)

    # Restore defaults so subsequent tests on the same worker see defaults
    keybindings = settings_page.click_on_keybindings()
    keybindings.reset_all_to_defaults()


@user_story("to find the Review All toggle in the Settings > Experimental section")
def test_settings_experimental_has_review_all_toggle(sculptor_instance_: SculptorInstance) -> None:
    """The Settings page should have an Experimental section with a Review All toggle."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    toggle = experimental.get_review_all_toggle()
    expect(toggle).to_be_visible()


@user_story("to toggle Review All on in Settings and see the button appear in the workspace")
def test_enable_review_all_via_settings_shows_button(sculptor_instance_: SculptorInstance) -> None:
    """Enabling enable_review_all via the Settings UI should make the Review All
    button visible when there are changes."""
    page = sculptor_instance_.page

    # Enable the setting via Settings UI before creating a workspace
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_review_all()

    # Create a workspace with uncommitted changes (navigates to the workspace)
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:write_file `{"file_path": "hello.py", "content": "print(\'hello\')"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # The Review All button should be visible since the setting is enabled
    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()
