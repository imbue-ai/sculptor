import time
from abc import ABC
from abc import abstractmethod
from collections import OrderedDict
from threading import Condition
from threading import Event
from threading import Lock
from threading import Thread
from typing import Generic
from typing import Hashable
from typing import TypeVar

from loguru import logger
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.concurrency_group import ConcurrencyExceptionGroup
from imbue_core.concurrency_group import ConcurrentShutdownError
from imbue_core.constants import ExceptionPriority
from imbue_core.log_utils import log_and_exit_program
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.time_utils import get_current_time
from sculptor.config.settings import SculptorSettings
from sculptor.constants import SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.agent import TaskStatusRunnerMessage
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.services.task_service.base_implementation import BaseTaskService
from sculptor.utils.errors import is_irrecoverable_exception

SHUTDOWN_TIMEOUT_SECONDS: float = 30.0
ERROR_BACKOFF_SECONDS: float = 0.5


class Runner(MutableModel):
    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        raise NotImplementedError()

    def stop(self) -> None:
        raise NotImplementedError()

    def join(self) -> None:
        raise NotImplementedError()

    def exception(self) -> BaseException | None:
        raise NotImplementedError()

    def get_name(self) -> str:
        raise NotImplementedError()


T = TypeVar("T", bound=Hashable)


class DebounceCache(Generic[T]):
    def __init__(self, interval_seconds: float, max_items=1024) -> None:
        self.cache: OrderedDict[T, float] = OrderedDict()
        self.max_items = max_items
        self.interval_seconds = interval_seconds

    def debounce(self, event: T, timestamp: float) -> bool:
        if event in self.cache and (timestamp - self.cache[event]) < self.interval_seconds:
            return False
        self.add(event, timestamp)
        return True

    def add(self, event: T, timestamp: float) -> None:
        if event in self.cache:
            # Move existing item to the end (latest time)
            self.cache.move_to_end(event)
            self.cache[event] = timestamp
        else:
            # Evict oldest item if at limit
            if len(self.cache) >= self.max_items:
                self.cache.popitem(last=False)
            self.cache[event] = timestamp


class ConcurrentTaskService(BaseTaskService, ABC):
    """This is the normal style of TaskService, which runs multiple tasks at once."""

    # Set this to true in tests to avoid actually running the task threads.
    # Also useful for when we are running a task in a separate process and don't want to spawn new tasks.
    is_spawner_suppressed: bool = False

    # This task runs on creation of DefaultTaskService and scans DataModelService for new tasks
    _spawner: Thread | None = PrivateAttr(default=None)
    _error_timestamps: DebounceCache = PrivateAttr(
        default_factory=lambda: DebounceCache(interval_seconds=ERROR_BACKOFF_SECONDS)
    )

    # Number of active task runners to have at once. If set to None, a run_task will be spawned for every task.
    # Note: this should ONLY be accessed or modified from inside the task spawner. Doing so elsewhere will race
    _runner_by_id: dict[TaskID, Runner] = PrivateAttr(default_factory=dict)
    _is_started: bool = PrivateAttr(default=False)
    _start_lock: Lock = PrivateAttr(default_factory=Lock)
    # Signal that a task has been created or restored (e.g. we might have new work to do).
    _new_or_restored_task_condition: Condition = PrivateAttr(default_factory=Condition)
    _has_outstanding_work: bool = PrivateAttr(default=False)

    def start(self) -> None:
        super().start()
        with self._start_lock:
            if self._is_started:
                return
            if not self.is_spawner_suppressed:
                # start the thread that will spawn tasks
                self._spawner = self.concurrency_group.start_new_thread(
                    target=self._spawn_run_tasks,
                    name=f"{self.__class__.__name__}::_spawn_run_tasks",
                    args=(self._shutdown_flag,),
                )
            self._is_started = True

    def stop(self) -> None:
        self._is_started = False
        self._shutdown_flag.set()
        # Wait for the spawner until it receives the shutdown flag and closes. We're okay to wait infinitely here
        if self._spawner is not None:
            self._spawner.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)

    def on_new_task(self, task: Task) -> None:
        super().on_new_task(task)
        with self._new_or_restored_task_condition:
            self._has_outstanding_work = True
            self._new_or_restored_task_condition.notify_all()

    def on_restore_task(self, task: Task) -> None:
        with self._new_or_restored_task_condition:
            self._has_outstanding_work = True
            self._new_or_restored_task_condition.notify_all()

    def _spawn_run_tasks(self, shutdown_flag: Event) -> None:
        logger.info("Started task spawning thread")
        # continue scheduling tasks until the shutdown flag is set
        activated_projects = set()
        while not shutdown_flag.is_set():
            try:
                with self._new_or_restored_task_condition:
                    if not self._has_outstanding_work:
                        # The timeout can't be too large or we'll be slow to shut down.
                        self._new_or_restored_task_condition.wait(1.0)
                    self._has_outstanding_work = False
                active_projects = self.project_service.get_active_projects()
                for project in active_projects:
                    if shutdown_flag.is_set():
                        break
                    if project.object_id not in activated_projects:
                        activated_projects.add(project.object_id)
                        self._clean_previously_running_tasks(project)
                    self._update(project)
            except Exception as e:
                if is_irrecoverable_exception(e):
                    logger.opt(exception=e).info(
                        "Irrecoverable error in task spawning thread. Terminating immediately."
                    )
                    log_exception(
                        e,
                        "Irrecoverable error in task spawning thread. Terminating immediately.",
                        priority=ExceptionPriority.LOW_PRIORITY,
                    )
                    log_and_exit_program(
                        SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR,
                        "Irrecoverable exception encountered (see logs for details).",
                    )
                if isinstance(e, ConcurrencyExceptionGroup) and e.only_exception_is_instance_of(
                    ConcurrentShutdownError
                ):
                    logger.info("Concurrency group was shut down, exiting task spawning thread.")
                    return
                # Otherwise, keep the task-spawning thread alive but log the error.
                if self._error_timestamps.debounce(type(e), time.monotonic()):
                    log_exception(e, "Error in task spawning thread")

        # The tasks should observe the shutdown flag and exit on their own.
        for runner_id, runner in self._runner_by_id.items():
            start = time.monotonic()
            logger.info("Attempting to join runner {} with id {}", runner.get_name(), runner_id)
            runner.join()
            end_time = time.monotonic()
            logger.info("Joined runner {} in {}s", runner.get_name(), end_time - start)

    def _update(self, project: Project) -> None:
        self._stop_expired_runners()
        self._clean_stopped_tasks()

        acknowledged_tasks = self._prepare_queued_tasks(project_id=project.object_id)

        # then start any new tasks
        self._register_runners_for_tasks(tasks=acknowledged_tasks)

    @abstractmethod
    def create_runner(self, task: Task, task_id: TaskID, settings: SculptorSettings) -> Runner:
        raise NotImplementedError()

    def _clean_previously_running_tasks(self, project: Project) -> None:
        # first, make sure that any tasks previously marked as RUNNING are now marked as QUEUED
        with self.data_model_service.open_task_transaction() as transaction:
            # get all tasks that are RUNNING
            running_tasks = transaction.get_tasks_for_project(
                outcomes={TaskState.RUNNING}, project_id=project.object_id
            )
            for task in running_tasks:
                # mark them as QUEUED so that they can be picked up again
                transaction.upsert_task(task.evolve(task.ref().outcome, TaskState.QUEUED))
                message = TaskStatusRunnerMessage(outcome=TaskState.QUEUED, message_id=AgentMessageID())
                self.create_message(message=message, task_id=task.object_id, transaction=transaction)

    def _prepare_queued_tasks(self, project_id: ProjectID) -> tuple[Task, ...]:
        # Retrieve a batch of tasks and mark them as RUNNING so that they're not retrieved again.
        with self.data_model_service.open_task_transaction() as transaction:
            existing_tasks = transaction.get_tasks_for_project(
                outcomes={TaskState.QUEUED}, project_id=project_id, max_results=100
            )
            acknowledged_tasks = tuple(task.evolve(task.ref().outcome, TaskState.RUNNING) for task in existing_tasks)
            for task in acknowledged_tasks:
                transaction.upsert_task(task)
                message = TaskStatusRunnerMessage(outcome=TaskState.RUNNING, message_id=AgentMessageID())
                self.create_message(message=message, task_id=task.object_id, transaction=transaction)
            return acknowledged_tasks

    def _stop_expired_runners(self):
        # then warn about any tasks that are running for too long
        for task_id, deadline in list(self._completion_deadline.items()):
            runner = self._runner_by_id[task_id]
            if runner.is_alive() and get_current_time() > deadline:
                logger.warning("Task {} is running for too long, shutting it down", task_id)
                runner.stop()
                runner.join()

    def _clean_stopped_tasks(self):
        # first clean up any tasks that are no longer running
        for task_id, runner in list(self._runner_by_id.items()):
            if not runner.is_alive():
                # remove the task from the list of running tasks
                logger.info("Runner with id {} is no longer alive", task_id)
                is_thread_runner = getattr(runner, "thread", False)
                if is_thread_runner:
                    logger.info(
                        "Thread runner with name '{}' died and we're now deleting it from `self._runner_by_id`",
                        runner.get_name(),
                    )
                del self._runner_by_id[task_id]
                if task_id in self._completion_deadline:
                    del self._completion_deadline[task_id]
                exception = runner.exception()
                if exception is not None and is_irrecoverable_exception(exception):
                    raise exception

    def _register_runners_for_tasks(self, tasks: tuple[Task, ...]) -> None:
        for task in tasks:
            task_id = task.object_id
            if task_id not in self._runner_by_id:
                # exceptions in here will definitely have been logged, see implementation of self._run_task
                logger.info("Creating runner:{}", self.settings)
                new_runner = self.create_runner(task, task_id, self.settings)
                self._runner_by_id[task_id] = new_runner
                new_runner.start()
                logger.info("Starting new runner with id {}", task_id)
