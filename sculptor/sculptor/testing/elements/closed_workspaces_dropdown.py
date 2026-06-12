from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightClosedWorkspacesDropdownElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the closed workspaces dropdown."""

    def get_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.CLOSED_WORKSPACE_ROW)

    def get_open_all_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.CLOSED_WORKSPACES_OPEN_ALL_BUTTON)

    def get_delete_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.CLOSED_WORKSPACE_DELETE_BUTTON)

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
