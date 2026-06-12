from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightActionsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Actions section in Settings."""

    def get_add_action_button(self) -> Locator:
        """Get the 'Add Action' toolbar button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_ADD_BUTTON)

    def get_add_group_button(self) -> Locator:
        """Get the 'Add Group' toolbar button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_ADD_GROUP_BUTTON)

    def get_export_button(self) -> Locator:
        """Get the 'Export' toolbar button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_EXPORT_BUTTON)

    def get_import_button(self) -> Locator:
        """Get the 'Import' toolbar button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_IMPORT_BUTTON)

    def get_action_rows(self) -> Locator:
        """Get all action setting rows."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTION_ROW)

    def get_action_row_by_name(self, name: str) -> Locator:
        """Find an action settings row by its text content."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTION_ROW).filter(has_text=name)

    def get_group_name_input(self) -> Locator:
        """Get the group name input in the Create Group dialog."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_GROUP_NAME_INPUT)

    def get_create_group_button(self) -> Locator:
        """Get the 'Create Group' confirm button in the dialog."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_CREATE_GROUP_BUTTON)

    def get_group_headings(self) -> Locator:
        """Get all group heading elements."""
        return self.get_by_test_id(ElementIDs.SETTINGS_ACTIONS_GROUP_HEADING)

    def get_action_edit_button(self, action_name: str) -> Locator:
        """Get the edit button for an action row by name."""
        row = self.get_action_row_by_name(action_name)
        return row.get_by_test_id(ElementIDs.SETTINGS_ACTION_EDIT_BUTTON)

    def get_action_delete_button(self, action_name: str) -> Locator:
        """Get the delete button for an action row by name."""
        row = self.get_action_row_by_name(action_name)
        return row.get_by_test_id(ElementIDs.SETTINGS_ACTION_DELETE_BUTTON)

    def confirm_delete_action(self) -> None:
        """Click the confirm button in the delete-action dialog."""
        confirm = self._page.get_by_test_id(ElementIDs.DELETE_ACTION_CONFIRM_BUTTON)
        expect(confirm).to_be_visible()
        confirm.click()

    def confirm_delete_group(self) -> None:
        """Click the confirm button in the delete-group dialog."""
        confirm = self._page.get_by_test_id(ElementIDs.DELETE_GROUP_CONFIRM_BUTTON)
        expect(confirm).to_be_visible()
        confirm.click()

    def click_delete_group(self, group_name: str) -> None:
        """Click the delete button for a group by name.

        Finds the group heading, navigates to its parent container,
        and clicks the delete (trash) icon button.
        """
        heading = self.get_group_headings().filter(has_text=group_name)
        expect(heading).to_be_visible()
        # The heading and delete button are siblings inside the same Flex container.
        # Navigate up to the container and find the delete button within it.
        delete_button = heading.locator("..").get_by_test_id(ElementIDs.SETTINGS_GROUP_DELETE_BUTTON)
        expect(delete_button).to_be_visible()
        delete_button.click()
