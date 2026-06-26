import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.backend_contract import TaskStatus
from sculptor.testing.constants import BUILD_TIMEOUT_SECONDS
from sculptor.testing.constants import RUNNING_TIMEOUT_SECONDS
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightTaskListElement(PlaywrightIntegrationTestElement):
    def get_tasks(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TASK_BUTTON)


def wait_for_tasks_to_build(
    task_list: PlaywrightTaskListElement,
    expected_task_count: int | None = None,
    is_unexpected_error_caused_by_test: bool = False,
) -> None:
    """Wait until all tasks are not 'Building', fail if any become 'Error'."""
    tasks = task_list.get_tasks()
    if expected_task_count is not None:
        expect(tasks).to_have_count(expected_task_count)

    for task in tasks.all():
        expect(task).not_to_have_attribute("data-status", TaskStatus.BUILDING, timeout=BUILD_TIMEOUT_SECONDS * 1000)
        if not is_unexpected_error_caused_by_test:
            expect(task).not_to_have_attribute("data-status", TaskStatus.ERROR)


def wait_for_tasks_to_finish(
    task_list: PlaywrightTaskListElement, is_unexpected_error_caused_by_test: bool = False
) -> None:
    """Wait for all tasks in the task list to be READY."""
    wait_for_tasks_to_build(task_list=task_list, is_unexpected_error_caused_by_test=is_unexpected_error_caused_by_test)

    # TODO[PROD-2442]: This only needs to use polling since there's a bug where the status flickers back to BUILDING
    # The loop below also has inconsistent timeouts for each task since this is not checked in threads
    for task in task_list.get_tasks().all():
        expect(task).to_have_attribute(
            "data-status",
            re.compile("|".join([TaskStatus.READY, TaskStatus.WAITING, TaskStatus.ERROR, TaskStatus.REQUEST_ERROR])),
            timeout=RUNNING_TIMEOUT_SECONDS * 1000,
        )
        if not is_unexpected_error_caused_by_test:
            expect(task).not_to_have_attribute("data-status", TaskStatus.ERROR)
