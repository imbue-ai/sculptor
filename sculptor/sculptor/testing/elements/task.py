from playwright.sync_api import Locator

from sculptor.testing.pages.task_page import PlaywrightTaskPage


def navigate_to_task_page(task: Locator) -> PlaywrightTaskPage:
    """Navigate to a task page by clicking on the task."""
    task.click()
    return PlaywrightTaskPage(page=task.page)
