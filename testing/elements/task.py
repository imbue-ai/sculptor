import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.task_page import PlaywrightTaskPage


def get_task_status_locator(task: Locator) -> Locator:
    return task.get_by_test_id(ElementIDs.TASK_STATUS)


def delete_task(task: Locator) -> None:
    # we need to select the task to make the actions menu button visible,
    # since the action menu button is hidden until hover or for the selected task
    task.click()
    task_actions_menu_button = task.get_by_test_id(ElementIDs.TASK_ACTIONS_MENU_BUTTON)
    task_actions_menu_button.click()

    # Wait for dropdown menu to appear and click delete
    # Dropdown menu is rendered at page level, not within task
    delete_menu_item = task.page.get_by_test_id(ElementIDs.DELETE_MENU_ITEM)
    delete_menu_item.click()

    # Wait for confirmation dialog and click confirm
    # Dialog is also rendered at page level
    confirm_delete_button = task.page.get_by_test_id(ElementIDs.CONFIRM_DELETE_BUTTON)
    confirm_delete_button.click()


def archive_task(task: Locator) -> None:
    # we need to select the task to make the actions menu button visible,
    # since the action menu button is hidden until hover or for the selected task
    task.click()
    task_actions_menu_button = task.get_by_test_id(ElementIDs.TASK_ACTIONS_MENU_BUTTON)
    task_actions_menu_button.click()

    # Wait for dropdown menu to appear and click archive
    # Dropdown menu is rendered at page level, not within task
    archive_menu_item = task.page.get_by_test_id(ElementIDs.ARCHIVE_MENU_ITEM)
    archive_menu_item.click()


def restore_task(task: Locator) -> None:
    # Click the task actions menu button
    task_actions_menu_button = task.get_by_test_id(ElementIDs.TASK_ACTIONS_MENU_BUTTON)
    task_actions_menu_button.click()

    # Wait for dropdown menu to appear and click restore
    # Dropdown menu is rendered at page level, not within task
    restore_menu_item = task.page.get_by_test_id(ElementIDs.RESTORE_MENU_ITEM)
    restore_menu_item.click()


def navigate_to_task_page(task: Locator) -> PlaywrightTaskPage:
    """Navigate to a task page by clicking on the task."""
    task.click()
    return PlaywrightTaskPage(page=task.page)


def get_task_branch_name(task: Locator) -> str:
    """Get the branch name from a task element.

    Waits for the data-branch-name attribute to be present and returns its value.
    """
    branch_element = task.get_by_test_id(ElementIDs.TASK_BRANCH)

    # Wait for the branch name attribute to be present (indicating non-null branch)
    expect(branch_element).to_have_attribute("data-branch-name", re.compile(r"..*"))

    # Get the branch name directly from the attribute
    branch_name = branch_element.get_attribute("data-branch-name")

    return branch_name
