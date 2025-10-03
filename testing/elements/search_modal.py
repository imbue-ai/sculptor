from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightSearchModalElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Search Modal component."""

    def get_input_element(self) -> Locator:
        """Get the search input element in the search modal."""
        return self.get_by_test_id(ElementIDs.SEARCH_MODAL_INPUT)

    def close(self):
        """Close the search modal."""
        self.get_by_test_id(ElementIDs.SEARCH_MODAL_CLOSE_BUTTON).click()
        expect(self).not_to_be_visible()

    def type_text(self, text: str):
        """Type a search query into the search input."""
        input_element = self.get_input_element()
        input_element.fill(text)

    def get_task_items(self) -> Locator:
        """Get all visible task items in the search results."""
        return self._page.get_by_test_id(ElementIDs.SEARCH_MODAL_TASK_ITEM)

    def select_task_by_index(self, index: int):
        """Click on a task by index to navigate to it."""
        task_items = self.get_task_items()
        task_items.nth(index).click()
        # Modal should close automatically after selection
        expect(self).not_to_be_visible()

    def press_arrow_down(self):
        """Press the down arrow key to navigate down in the list."""
        self.get_input_element().press("ArrowDown")

    def press_arrow_up(self):
        """Press the up arrow key to navigate up in the list."""
        self.get_input_element().press("ArrowUp")

    def press_enter(self):
        """Press Enter to select the currently highlighted task."""
        self.get_input_element().press("Enter")
        # Modal should close automatically after selection
        expect(self).not_to_be_visible()

    def press_escape(self):
        """Press Escape to close the modal."""
        self.get_input_element().press("Escape")
        expect(self).not_to_be_visible()

    def get_selected_task_index(self) -> int | None:
        """Get the index of the currently selected task, or None if no task is selected."""
        found_index = None
        task_items = self.get_task_items()
        for i in range(task_items.count()):
            task = task_items.nth(i)
            is_selected = task.get_attribute("data-is-selected")
            if is_selected == "true":
                assert found_index is None, "Multiple tasks are marked as selected."
                found_index = i
        return found_index

    def assert_x_selected(self, expected_index: int):
        """Assert that the task at expected_index is selected."""
        actual_index = self.get_selected_task_index()
        assert actual_index == expected_index, (
            f"Expected index {expected_index} to be selected, but got {actual_index}."
        )

    def hover_task_by_index(self, index: int):
        """Hover over a task by index to select it with mouse."""
        task_items = self.get_task_items()
        task_items.nth(index).hover()

    def wait_for_no_tasks_message(self):
        """Wait for the 'No tasks found' message to appear."""
        no_tasks_element = self._page.get_by_test_id(ElementIDs.SEARCH_MODAL_NO_TASKS)
        expect(no_tasks_element).to_be_visible()
