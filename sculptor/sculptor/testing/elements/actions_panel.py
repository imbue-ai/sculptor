from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightActionsPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Actions panel in the workspace."""

    def get_add_button(self) -> Locator:
        """Get the '+' button in the panel header."""
        return self.get_by_test_id(ElementIDs.ACTIONS_PANEL_ADD_BUTTON)

    def get_action_chips(self) -> Locator:
        """Get all action chip buttons."""
        return self.get_by_test_id(ElementIDs.ACTION_CHIP)

    def get_action_chip_by_name(self, name: str) -> Locator:
        """Find an action chip by its text label."""
        return self.get_by_test_id(ElementIDs.ACTION_CHIP).filter(has_text=name)

    def get_group_header_by_name(self, name: str) -> Locator:
        """Find a group header by its text label."""
        return self.get_by_test_id(ElementIDs.ACTIONS_PANEL_GROUP_HEADER).filter(has_text=name)

    def get_group_context_menu_delete_item(self) -> Locator:
        """Get the 'Delete group' item from the context menu."""
        return self._page.get_by_test_id(ElementIDs.GROUP_CONTEXT_MENU_DELETE)

    def confirm_delete_group(self) -> None:
        """Click the confirm button in the delete-group dialog."""
        confirm = self._page.get_by_test_id(ElementIDs.DELETE_GROUP_CONFIRM_BUTTON)
        expect(confirm).to_be_visible()
        confirm.click()

    def delete_group_via_context_menu(self, group_name: str) -> None:
        """Right-click a group header and select 'Delete group' from the context menu."""
        header = self.get_group_header_by_name(group_name)
        expect(header).to_be_visible()
        header.click(button="right")
        delete_item = self._page.get_by_test_id(ElementIDs.GROUP_CONTEXT_MENU_DELETE)
        expect(delete_item).to_be_visible()
        delete_item.click()
