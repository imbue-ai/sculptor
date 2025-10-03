import signal
from subprocess import Popen

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.services.task_service.concurrent_implementation import ConcurrentTaskService
from sculptor.services.task_service.concurrent_implementation import Runner
from sculptor.services.task_service.concurrent_implementation import SHUTDOWN_TIMEOUT_SECONDS


class ProcessRunner(Runner):
    process: Popen

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)

    def join(self) -> None:
        exit_code = self.process.wait(SHUTDOWN_TIMEOUT_SECONDS / 2.0)
        if exit_code is None:
            self.process.send_signal(signal.SIGTERM)
            exit_code = self.process.wait(SHUTDOWN_TIMEOUT_SECONDS / 2.0)
            assert exit_code is not None, "Process did not terminate in time"

    def exception(self) -> BaseException | None:
        raise NotImplementedError()


# TODO: implement this in order to allow running tasks in a local process
class LocalProcessTaskService(ConcurrentTaskService):
    def create_runner(self, task: Task, task_id: TaskID, settings: SculptorSettings) -> ProcessRunner:
        raise NotImplementedError()
