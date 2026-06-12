from typing import Callable

from pydantic import PrivateAttr

from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.thread_utils import ObservableThread
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.services.task_service.concurrent_implementation import ConcurrentTaskService
from sculptor.services.task_service.concurrent_implementation import Runner
from sculptor.services.task_service.data_types import ServiceCollectionForTask


class ThreadRunner(Runner):
    concurrency_group: ConcurrencyGroup
    name: str
    args: tuple[Task, ServiceCollectionForTask, SculptorSettings, ConcurrencyGroup]
    target: Callable[[Task, ServiceCollectionForTask, SculptorSettings, ConcurrencyGroup], None]
    _thread: ObservableThread | None = PrivateAttr(default=None)

    def __str__(self) -> str:
        # Don't try to serialize the concurrency group or the target function.
        return f"ThreadRunner(name={self.name}, is_alive={self.is_alive()})"

    def __repr__(self) -> str:
        return self.__str__()

    def start(self) -> None:
        self._thread = self.concurrency_group.start_new_thread(
            target=self.target,
            args=self.args,
            name=self.name,
            suppressed_exceptions=(BaseException,),
        )

    def is_alive(self) -> bool:
        if self._thread is None:
            return False
        return self._thread.is_alive()

    def stop(self) -> None:
        pass

    def join(self, timeout: float | None = None) -> None:
        assert self._thread is not None
        # send the shutdown signal to the task
        self._thread.join(timeout)

    def exception(self) -> BaseException | None:
        if self._thread is None:
            return None
        return self._thread._exception

    def get_name(self) -> str:
        if self._thread is None:
            return self.name
        return f"{self.name} ({self._thread.target_name})"


def _get_name_for_runner_from_task(task: Task, task_id: TaskID) -> str:
    class_name = task.input_data.__class__.__name__
    class_name = class_name.replace("Inputs", "")
    class_name = class_name.replace("V1", "")
    return f"TaskRunner-{class_name}-{task_id}"


class LocalThreadTaskService(ConcurrentTaskService):
    def create_runner(self, task: Task, task_id: TaskID, settings: SculptorSettings) -> Runner:
        new_runner = ThreadRunner(
            concurrency_group=self.concurrency_group,
            target=self._run_task,
            args=(task, self._get_services_for_task(), settings, self.concurrency_group),
            name=_get_name_for_runner_from_task(task, task_id),
        )
        return new_runner
