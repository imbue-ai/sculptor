"""Integration tests for the Theme Builder settings page."""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance


def test_theme_builder_navigation(sculptor_instance_: SculptorInstance):
    """Test that the Theme Builder section is navigable and renders all controls."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    theme_builder = settings_page.click_on_theme_builder()

    expect(theme_builder.get_accent_color_control()).to_be_visible()
    expect(theme_builder.get_gray_color_control()).to_be_visible()
    expect(theme_builder.get_appearance_control()).to_be_visible()
    expect(theme_builder.get_radius_control()).to_be_visible()
    expect(theme_builder.get_scaling_control()).to_be_visible()
    expect(theme_builder.get_panel_background_control()).to_be_visible()
    expect(theme_builder.get_danger_color_control()).to_be_visible()
    expect(theme_builder.get_success_color_control()).to_be_visible()
    expect(theme_builder.get_warning_color_control()).to_be_visible()
    expect(theme_builder.get_info_color_control()).to_be_visible()
    expect(theme_builder.get_reset_button()).to_be_visible()


def test_theme_builder_change_accent_color(sculptor_instance_: SculptorInstance):
    """Test that changing the accent color persists across navigations."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    theme_builder = settings_page.click_on_theme_builder()

    theme_builder.expect_accent_color("gray")

    theme_builder.select_accent_color("blue")
    theme_builder.expect_accent_color("blue")

    # Navigate away to General and back to Theme Builder — value should persist
    settings_page.click_on_general()
    theme_builder = settings_page.click_on_theme_builder()

    theme_builder.expect_accent_color("blue")


def test_theme_builder_reset_to_defaults(sculptor_instance_: SculptorInstance):
    """Test that the Reset button restores all settings to their defaults."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    theme_builder = settings_page.click_on_theme_builder()

    theme_builder.select_accent_color("blue")
    theme_builder.select_danger_color("crimson")

    theme_builder.expect_accent_color("blue")
    theme_builder.expect_danger_color("crimson")

    theme_builder.click_reset()

    theme_builder.expect_accent_color("gray")
    theme_builder.expect_danger_color("tomato")
    theme_builder.expect_gray_color("gray")
    theme_builder.expect_radius("medium")
    theme_builder.expect_scaling("100%")
