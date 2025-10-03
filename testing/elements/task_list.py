import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.constants import BUILD_TIMEOUT_SECS
from sculptor.testing.constants import RUNNING_TIMEOUT_SECS
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.web.derived import TaskStatus


class PlaywrightTaskListElement(PlaywrightIntegrationTestElement):
    def get_tasks(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TASK_BUTTON)


def wait_for_tasks_to_build(task_list: PlaywrightTaskListElement, expected_num_tasks: int | None = None) -> None:
    """Wait until all tasks are not 'Building', fail if any become 'Error'."""
    tasks = task_list.get_tasks()
    if expected_num_tasks is not None:
        expect(tasks).to_have_count(expected_num_tasks)

    for task in tasks.all():
        expect(task).not_to_have_attribute("data-status", TaskStatus.BUILDING, timeout=BUILD_TIMEOUT_SECS * 1000)
        expect(task).not_to_have_attribute("data-status", TaskStatus.ERROR)


def wait_for_tasks_to_finish(task_list: PlaywrightTaskListElement) -> None:
    """Wait for all tasks in the task list to be READY."""
    wait_for_tasks_to_build(task_list=task_list)

    # TODO[PROD-2442]: This only needs to use polling since there's a bug where the status flickers back to BUILDING
    # The loop below also has inconsistent timeouts for each task since checking this in threads seems overkill
    for task in task_list.get_tasks().all():
        expect(task).to_have_attribute(
            "data-status",
            re.compile("|".join([TaskStatus.READY, TaskStatus.ERROR])),
            timeout=RUNNING_TIMEOUT_SECS * 1000,
        )
        expect(task).not_to_have_attribute("data-status", TaskStatus.ERROR)
