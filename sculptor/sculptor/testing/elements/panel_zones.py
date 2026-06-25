"""Panel zone layout element POM for integration tests.

Provides a POM for interacting with the panel zone layout system:
sidebar icons, zone containers, context menus, and resize handles.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs


class PlaywrightPanelZonesElement:
    """POM for the panel zone layout: sidebar icons, zone containers,
    context menus, and resize handles."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_actions_icon(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_ICON_ACTIONS)

    def get_files_icon(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_ICON_FILES)

    def get_skills_icon(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_ICON_SKILLS)

    def get_terminal_icon(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_ICON_TERMINAL)

    def get_top_right_zone(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_TOP_RIGHT)

    def get_bottom_right_zone(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_BOTTOM_RIGHT)

    def get_right_area(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_RIGHT_AREA)

    def get_right_resize_handle(self) -> Locator:
        return self.get_right_area().get_by_test_id(ElementIDs.PANEL_RIGHT_RESIZE_HANDLE)

    def get_side_toggle_left(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SIDE_TOGGLE_LEFT)

    def get_side_toggle_bottom(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SIDE_TOGGLE_BOTTOM)

    def get_side_toggle_right(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SIDE_TOGGLE_RIGHT)

    def get_focus_mode_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.FOCUS_MODE_BUTTON)

    def get_configure_context_menu_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_CONTEXT_MENU_CONFIGURE)

    def get_file_browser_panel(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)

    def get_plugin_panel_icon(self, plugin_id: str) -> Locator:
        """Locator for a plugin-contributed panel's sidebar icon.

        Plugin panels render `data-panel-icon=<id>` with no ElementIDs testid
        (unlike built-in panels, which are in PANEL_ICON_TEST_IDS), so they're
        located by that attribute.
        """
        return self._page.locator(f'[data-panel-icon="{plugin_id}"]')

    def activate_plugin_panel(self, plugin_id: str) -> None:
        """Click a plugin-contributed panel's sidebar icon to make it the active
        panel in its zone."""
        icon = self.get_plugin_panel_icon(plugin_id)
        expect(icon).to_be_visible()
        icon.click()

    def move_panel_to_zone(self, panel_icon_id: ElementIDs, zone_key: str) -> None:
        """Move a panel to a different zone via its sidebar icon context menu.

        Right-clicks the panel's sidebar icon, hovers "Move to", and selects
        the target zone.  The panel must already be registered (icon visible
        in the sidebar).
        """
        icon = self._page.get_by_test_id(panel_icon_id)
        expect(icon).to_be_visible()
        icon.click(button="right")
        move_to = self._page.get_by_test_id(ElementIDs.PANEL_CONTEXT_MENU_MOVE_TO)
        expect(move_to).to_be_visible()
        move_to.hover()
        zone_option = self._page.get_by_test_id(f"{ElementIDs.PANEL_CONTEXT_MENU_ZONE_OPTION}-{zone_key}")
        expect(zone_option).to_be_visible()
        zone_option.click()
