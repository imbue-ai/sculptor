from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.hotkey_field import PlaywrightHotkeyFieldElement


class PlaywrightPanelsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Panels Settings section."""

    def get_panel_row(self, panel_id: str) -> Locator:
        """Find a panel row by its data-panel-row-id attribute."""
        return self._locator.locator(f'[data-panel-row-id="{panel_id}"]')

    def set_panel_enabled(self, panel_id: str, enabled: bool) -> None:
        """Toggle the on/off Switch for a panel. No-op for builtin panels (no Switch rendered)."""
        switch = self._locator.get_by_test_id(f"{ElementIDs.SETTINGS_PANELS_ENABLED_SWITCH}-{panel_id}")
        # Radix Switch's checked state mirrors data-state="checked" / "unchecked"
        is_checked = switch.get_attribute("data-state") == "checked"
        if is_checked != enabled:
            switch.click()

    def set_panel_zone(self, panel_id: str, zone_id: str) -> None:
        """Open the zone Select for a panel and pick `zone_id`."""
        trigger = self._locator.get_by_test_id(f"{ElementIDs.SETTINGS_PANELS_ZONE_SELECT}-{panel_id}")
        trigger.click()
        # Radix Select renders options in a portal, so query at the page level.
        # exact=True avoids matching e.g. "bottom" against "Bottom Left" / "Bottom Right".
        self._page.get_by_role("option", name=_zone_label(zone_id), exact=True).click()

    def set_panel_shortcut(self, panel_id: str, keys: str) -> None:
        """Record a shortcut on the panel row."""
        self._get_panel_hotkey(panel_id).set_hotkey(keys)

    def clear_panel_shortcut(self, panel_id: str) -> None:
        """Clear the shortcut on the panel row."""
        self._get_panel_hotkey(panel_id).clear_hotkey()

    def get_conflict_warning(self) -> Locator:
        """Return the conflict warning locator (shared element id with the Keybindings page)."""
        return self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_CONFLICT_WARNING)

    def click_reassign(self) -> None:
        """Click the 'Reassign' button in the conflict warning."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_REASSIGN).click()

    def click_cancel_conflict(self) -> None:
        """Click the 'Cancel' button in the conflict warning."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_KEYBINDINGS_CANCEL_CONFLICT).click()

    def reset_to_defaults(self) -> None:
        """Click the 'Reset to defaults' button."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_PANELS_RESET_DEFAULTS).click()

    def click_diagram_zone(self, zone_id: str) -> None:
        """Click a zone in the diagram to filter the panel list."""
        self._locator.get_by_test_id(f"{ElementIDs.SETTINGS_PANELS_DIAGRAM_ZONE}-{zone_id}").click()

    def click_clear_zone_filter(self) -> None:
        """Click the button that clears the diagram zone filter."""
        self._locator.get_by_test_id(ElementIDs.SETTINGS_PANELS_DIAGRAM_CLEAR_FILTER).click()

    def get_zone_select_trigger(self, panel_id: str) -> Locator:
        """Return the zone select trigger for a panel row."""
        return self._locator.get_by_test_id(f"{ElementIDs.SETTINGS_PANELS_ZONE_SELECT}-{panel_id}")

    def drag_diagram_icon(self, panel_id: str, target_zone_id: str) -> None:
        """Drag a panel icon from its current zone to `target_zone_id` in the diagram.

        Uses a slow manual mouse sequence because dnd-kit's PointerSensor requires
        a minimum movement distance (5 px) before activation; Playwright's built-in
        drag_to does not always satisfy that constraint.
        """
        source = self._locator.get_by_test_id(f"{ElementIDs.SETTINGS_PANELS_DIAGRAM_ICON}-{panel_id}")
        target = self._locator.get_by_test_id(f"{ElementIDs.SETTINGS_PANELS_DIAGRAM_ZONE}-{target_zone_id}")

        src_box = source.bounding_box()
        tgt_box = target.bounding_box()
        if src_box is None or tgt_box is None:
            raise AssertionError(f"Could not get bounding boxes for drag: {panel_id} → {target_zone_id}")

        src_x = src_box["x"] + src_box["width"] / 2
        src_y = src_box["y"] + src_box["height"] / 2
        tgt_x = tgt_box["x"] + tgt_box["width"] / 2
        tgt_y = tgt_box["y"] + tgt_box["height"] / 2

        self._page.mouse.move(src_x, src_y)
        self._page.mouse.down()
        # Move in small steps so dnd-kit's PointerSensor (distance: 5) activates.
        self._page.mouse.move(tgt_x, tgt_y, steps=20)
        self._page.mouse.up()

    def _get_panel_hotkey(self, panel_id: str) -> PlaywrightHotkeyFieldElement:
        return PlaywrightHotkeyFieldElement(locator=self.get_panel_row(panel_id), page=self._page)


_ZONE_LABELS = {
    "top-left": "Top Left",
    "bottom-left": "Bottom Left",
    "bottom": "Bottom",
    "top-right": "Top Right",
    "bottom-right": "Bottom Right",
}


def _zone_label(zone_id: str) -> str:
    return _ZONE_LABELS[zone_id]
