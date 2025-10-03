from imbue_core.common import is_running_within_a_pytest_tree
from imbue_core.thread_utils import ObservableThread
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.services.task_service.concurrent_implementation import ConcurrentTaskService
from sculptor.services.task_service.concurrent_implementation import Runner


class ThreadRunner(Runner):
    thread: ObservableThread

    def start(self) -> None:
        self.thread.start()

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def stop(self) -> None:
        pass

    def join(self, timeout: float | None = None) -> None:
        # send the shutdown signal to the task
        self.thread.join(timeout)

    def exception(self) -> BaseException | None:
        return self.thread._exception


def _get_name_for_runner_from_task(task: Task, task_id: TaskID) -> str:
    class_name = task.input_data.__class__.__name__
    class_name = class_name.replace("Inputs", "")
    class_name = class_name.replace("V1", "")
    return f"TaskRunner-{class_name}-{task_id}"


class LocalThreadTaskService(ConcurrentTaskService):
    def create_runner(self, task: Task, task_id: TaskID, settings: SculptorSettings) -> Runner:
        new_runner = ThreadRunner(
            thread=ObservableThread(
                target=self._run_task,
                args=(task, self._get_services_for_task(), settings),
                name=_get_name_for_runner_from_task(task, task_id),
                suppressed_exceptions=(BaseException,),
            )
        )
        return new_runner

    def stop(self) -> None:
        if is_running_within_a_pytest_tree():
            super().stop()
