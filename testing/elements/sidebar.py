from pathlib import Path

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.project_selector import PlaywrightProjectSelectorElement
from sculptor.testing.elements.task_list import PlaywrightTaskListElement


class PlaywrightSidebarElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Sidebar component."""

    # ==========================================
    # Low level Element Getters
    # ==========================================

    def get_task_list(self) -> PlaywrightTaskListElement:
        """Get the task list within the sidebar - reuses existing TaskListElement implementation."""
        task_list = self.get_by_test_id(ElementIDs.TASK_LIST)
        return PlaywrightTaskListElement(locator=task_list, page=self._page)

    def get_project_selector(self) -> PlaywrightProjectSelectorElement:
        """Get the project selector element."""
        project_selector = self.get_by_test_id(ElementIDs.PROJECT_SELECTOR)
        return PlaywrightProjectSelectorElement(locator=project_selector, page=self._page)

    def get_home_button(self) -> Locator:
        """Get the home navigation button."""
        return self.get_by_test_id(ElementIDs.HOME_BUTTON)

    def get_new_agent_button(self) -> Locator:
        """Get the New Agent button."""
        return self.get_by_test_id(ElementIDs.NEW_AGENT_BUTTON)

    def get_view_archived_button(self) -> Locator:
        """Get the view archived tasks button."""
        return self.get_by_test_id(ElementIDs.VIEW_ARCHIVED_TASKS_BUTTON)

    def get_back_to_active_button(self) -> Locator:
        """Get the back to active agents button (shown when viewing archived)."""
        return self.get_by_test_id(ElementIDs.BACK_TO_ACTIVE_AGENTS_BUTTON)

    def get_settings_button(self) -> Locator:
        """Get the settings button."""
        return self.get_by_test_id(ElementIDs.SETTINGS_BUTTON)

    def get_search_modal_button(self) -> Locator:
        """Get the search modal open button."""
        return self.get_by_test_id(ElementIDs.SEARCH_MODAL_OPEN_BUTTON)

    def get_search_input(self) -> Locator:
        """Get the task search input field."""
        # The search input is a TextField.Root, we need to find the actual input element
        return self.locator("input[placeholder='Search tasks...']")

    def get_tasks(self) -> Locator:
        """Convenience method to get all tasks directly."""
        return self.get_task_list().get_tasks()

    # ==========================================
    # High level Interactions
    # ==========================================

    def is_showing_archived_view(self) -> bool:
        """Check if currently showing archived tasks view."""
        back_button = self.get_back_to_active_button()
        try:
            expect(back_button).to_be_visible()
            return True
        except AssertionError:
            return False

    def ensure_archived_view_is_open(self) -> None:
        """Ensure the archived tasks view is open."""
        if not self.is_showing_archived_view():
            self.get_view_archived_button().click()

    def ensure_active_view_is_open(self) -> None:
        """Ensure the active tasks view is open."""
        if self.is_showing_archived_view():
            self.get_back_to_active_button().click()

    def search_tasks(self, query: str) -> None:
        """Search for tasks by typing in the search input."""
        search_input = self.get_search_input()
        search_input.fill(query)

    def clear_search(self) -> None:
        """Clear the search input."""
        search_input = self.get_search_input()
        search_input.clear()

    def click_new_agent_button(self) -> None:
        """Click the New Agent button."""
        self.get_new_agent_button().click()

    def navigate_to_home(self) -> None:
        """Click the home button to navigate to home page."""
        self.get_home_button().click()

    def open_search_modal(self) -> None:
        """Click the search button to open the search modal."""
        self.get_search_modal_button().click()

    def get_task_by_index(self, index: int) -> Locator:
        """Get a task by its index in the list."""
        tasks = self.get_tasks()
        return tasks.nth(index)

    def click_task_by_index(self, index: int) -> None:
        """Click a task by its index to navigate to it."""
        task = self.get_task_by_index(index)
        task.click()

    def get_task_count(self) -> int:
        """Get the number of visible tasks."""
        tasks = self.get_tasks()
        return tasks.count()

    def create_project(self, project_path: Path, project_name: str | None = None) -> None:
        """
        Create a project through the sidebar UI.

        This encapsulates the common flow of:
        1. Clicking "Open New Repo" via project selector
        2. Entering the project path
        3. Handling the dialog
        4. Waiting for the project to load

        Args:
            project_path: Path to the project directory
            project_name: Expected project name (defaults to directory name)
        """
        if project_name is None:
            project_name = project_path.name

        # Get the project selector and open the dialog
        project_selector = self.get_project_selector()
        project_selector.open_new_repo_dialog()

        # Wait for and fill the dialog
        dialog = self._page.get_by_test_id(ElementIDs.OPEN_NEW_REPO_DIALOG)
        expect(dialog).to_be_visible()

        # Find the input field and enter the path
        input_field = self._page.get_by_test_id(ElementIDs.OPEN_NEW_REPO_INPUT)
        input_field.fill(str(project_path.resolve()))

        # Click the confirm button
        confirm_button = dialog.get_by_test_id(ElementIDs.CONFIRM_OPEN_NEW_REPO_BUTTON)
        confirm_button.click()

        # Wait for the project to be loaded - check that it appears in the selector
        expect(project_selector.get_selector_trigger()).to_contain_text(project_name)

    def select_project_by_name(self, project_name: str) -> None:
        """Select a different project by name using the project selector."""
        project_selector = self.get_project_selector()
        project_selector.select_project_by_name(project_name)


# ==========================================
# Helper Functions for Common Operations
# ==========================================


def wait_for_sidebar_to_load(sidebar: PlaywrightSidebarElement) -> None:
    """Wait for the sidebar to fully load with all its elements."""
    expect(sidebar).to_be_visible()


def navigate_to_task_from_sidebar(sidebar: PlaywrightSidebarElement, task_index: int = 0) -> None:
    """Navigate to a task from the sidebar - replacement for old home page navigation."""
    wait_for_sidebar_to_load(sidebar)
    sidebar.click_task_by_index(task_index)
