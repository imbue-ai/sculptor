from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightThemeBuilderSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Theme Builder Settings section.

    The Theme Builder uses three kinds of controls:
    - ColorSwatchPicker (accent, gray, danger, success, warning, info): a ``div[role="radiogroup"]``
      containing ``div[role="radio"]`` items with ``aria-label`` and ``aria-checked``.
    - RadiusPreviewPicker (radius): same radiogroup/radio pattern as swatch pickers.
    - SegmentedControl (appearance, scaling, panel background): Radix ``SegmentedControl`` with
      ``button[role="radio"][data-state="on"|"off"]`` items containing text labels.
    """

    # --- Selection methods ---

    def select_accent_color(self, color: str) -> None:
        """Select an accent color from the swatch picker."""
        self._click_radio(self._get_accent_color_group(), color)

    def select_danger_color(self, color: str) -> None:
        """Select a danger color from the swatch picker."""
        self._click_radio(self._get_danger_color_group(), color)

    def click_reset(self) -> None:
        """Click the 'Reset to defaults' button."""
        self._get_reset_button().click()

    # --- Assertion methods ---

    def expect_accent_color(self, color: str) -> None:
        """Assert the currently selected accent color matches the expected value."""
        self._expect_radio_checked(self._get_accent_color_group(), color)

    def expect_gray_color(self, color: str) -> None:
        """Assert the currently selected gray color matches the expected value."""
        self._expect_radio_checked(self._get_gray_color_group(), color)

    def expect_danger_color(self, color: str) -> None:
        """Assert the currently selected danger color matches the expected value."""
        self._expect_radio_checked(self._get_danger_color_group(), color)

    def expect_radius(self, radius: str) -> None:
        """Assert the currently selected radius matches the expected value."""
        self._expect_radio_checked(self._get_radius_group(), radius)

    def expect_scaling(self, scaling: str) -> None:
        """Assert the currently selected scaling matches the expected value."""
        self._expect_segment_active(self._get_scaling_control(), scaling)

    # --- Public locator getters ---

    def get_accent_color_control(self) -> Locator:
        return self._get_accent_color_group()

    def get_gray_color_control(self) -> Locator:
        return self._get_gray_color_group()

    def get_appearance_control(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_APPEARANCE)

    def get_radius_control(self) -> Locator:
        return self._get_radius_group()

    def get_scaling_control(self) -> Locator:
        return self._get_scaling_control()

    def get_panel_background_control(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_PANEL_BACKGROUND)

    def get_danger_color_control(self) -> Locator:
        return self._get_danger_color_group()

    def get_success_color_control(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_SUCCESS_COLOR)

    def get_warning_color_control(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_WARNING_COLOR)

    def get_info_color_control(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_INFO_COLOR)

    def get_reset_button(self) -> Locator:
        return self._get_reset_button()

    # --- Private interaction helpers ---

    def _click_radio(self, group: Locator, value: str) -> None:
        """Click a radio button in a swatch/radius picker by its aria-label."""
        group.get_by_role("radio", name=value, exact=True).click()

    def _expect_radio_checked(self, group: Locator, value: str) -> None:
        """Assert that the radio with the given aria-label is checked in a radiogroup."""
        expect(group.get_by_role("radio", name=value, exact=True)).to_have_attribute("aria-checked", "true")

    def _expect_segment_active(self, control: Locator, value: str) -> None:
        """Assert that the segment with the given value is active in a SegmentedControl."""
        expect(control.locator(f'button[role="radio"]:has-text("{value}")').first).to_have_attribute(
            "data-state", "on"
        )

    # --- Private locator getters ---

    def _get_accent_color_group(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_ACCENT_COLOR)

    def _get_gray_color_group(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_GRAY_COLOR)

    def _get_radius_group(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_RADIUS)

    def _get_scaling_control(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_SCALING)

    def _get_danger_color_group(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_DANGER_COLOR)

    def _get_reset_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SETTINGS_THEME_BUILDER_RESET)
