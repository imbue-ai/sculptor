import threading
import time
from contextlib import contextmanager
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Event
from typing import Any
from typing import Callable
from typing import Generator
from typing import TypeVar
from typing import assert_never
from typing import cast

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.errors import ExpectedError
from imbue_core.sculptor.state.messages import Message
from imbue_core.thread_utils import ObservableThread
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import CacheReposInputsV1
from sculptor.database.models import CleanupImagesInputsV1
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import SendEmailTaskInputsV1
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import UserSettings
from sculptor.interfaces.agents.v1.agent import PartialResponseBlockAgentMessage
from sculptor.primitives.constants import USER_FACING_LOG_TYPE
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.threads import StopGapBackgroundPollingStreamSource
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.git_repo_service.api import ReadOnlyGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.task_service.errors import TaskNotFound
from sculptor.utils.jsonl_logs import observe_jsonl_log_file
from sculptor.web.auth import UserSession
from sculptor.web.derived import CacheReposTaskView
from sculptor.web.derived import CleanupImagesTaskView
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import LocalRepoInfo
from sculptor.web.derived import SendEmailTaskView
from sculptor.web.derived import TaskListUpdate
from sculptor.web.derived import TaskUpdate
from sculptor.web.derived import TaskViewTypes
from sculptor.web.derived import UserUpdate
from sculptor.web.message_conversion import convert_agent_messages_to_task_update

T = TypeVar("T")
TaskUpdateTypes = Message | CompletedTransaction | dict[str, Any]
TaskListUpdateTypes = TaskMessageContainer | CompletedTransaction | SculptorSettings
UserUpdateSourceTypes = LocalRepoInfo | CompletedTransaction | SculptorSettings

_KEEPALIVE_SECONDS = 10
_POLL_SECONDS = 1

# TODO: delete when stopgap polling is migrated to a watcher
_GIT_STATUS_POLL_SECONDS = 3.0


class ServerStopped(Exception):
    pass


def stream_user_updates(
    user_session: UserSession,
    project_id: ProjectID,
    shutdown_event: Event,
    services: CompleteServiceCollection,
) -> Generator[UserUpdate | None, None, None]:
    user_ref = user_session.user_reference
    org_ref = user_session.organization_reference
    get_repo_status_and_state_backup = _LocalRepoInfoExfiltrationCallback(services, user_ref, project_id)
    updates_queue: Queue[UserUpdateSourceTypes] = Queue()
    with (
        services.data_model_service.observe_user_changes(user_ref, org_ref, updates_queue),
        stream_repo_info_updates_via_polling(get_repo_status_and_state_backup, updates_queue),
    ):
        # read everything out that's already in the queue and let the front end know about the current state
        earlier_data = _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=False)
        earlier_data.append(services.settings)
        yield _convert_to_user_update(earlier_data)

        current_repo_info = get_repo_status_and_state_backup()
        if current_repo_info:
            yield _convert_to_user_update([current_repo_info])

        # finally, just keep reading from the queue
        while True:
            new_data = _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=True)
            yield _convert_to_user_update(new_data)


def _convert_to_user_update(all_data: list[UserUpdateSourceTypes]) -> UserUpdate:
    """Converts a list of models into a UserUpdate."""
    if len(all_data) == 0:
        return UserUpdate()
    notifications: list[Notification] = []
    projects_by_id: dict[ProjectID, Project] = {}
    user_settings = None
    server_settings = None
    finished_request_ids = []
    repo_info = None
    for model in all_data:
        if model is None:
            continue
        match model:
            case CompletedTransaction():
                completed_transaction = model
                if completed_transaction.request_id is not None:
                    finished_request_ids.append(completed_transaction.request_id)
                for request_model in completed_transaction.updated_models:
                    match request_model:
                        case Notification():
                            notifications.append(request_model)
                        case Project():
                            projects_by_id[request_model.object_id] = request_model
                        case UserSettings():
                            user_settings = request_model
                        case _ as unreachable:
                            assert_never(unreachable)
            case SculptorSettings():
                server_settings = model
            case LocalRepoInfo():
                repo_info = model
            case None:
                pass
            case _ as unreachable:
                assert_never(unreachable)
    return UserUpdate(
        user_settings=user_settings,
        projects=tuple(projects_by_id.values()),
        notifications=tuple(notifications),
        finished_request_ids=tuple(finished_request_ids),
        settings=server_settings,
        local_repo_info=repo_info,
    )


def stream_task(
    task_id_str: str, user_session: UserSession, shutdown_event: Event, services: CompleteServiceCollection
) -> Generator[TaskUpdate, None, None]:
    # first, subscribe to the task updates
    task_id = TaskID(task_id_str)
    with services.task_service.subscribe_to_task(task_id) as updates_queue:
        updates_queue = cast(Queue[TaskUpdateTypes], updates_queue)
        # next, subscribe to any data model updates for this task
        with services.data_model_service.observe_user_changes(
            user_reference=user_session.user_reference,
            organization_reference=user_session.organization_reference,
            queue=updates_queue,
        ):
            # finally, subscribe to new log messages for this task
            with _observe_new_logs_for_task(task_id=task_id, queue=updates_queue, settings=services.settings):
                # get the current task object
                with user_session.open_transaction(services) as transaction:
                    task = services.task_service.get_task(task_id, transaction)
                if not task:
                    raise TaskNotFound(f"Task {task_id} not found")
                # read everything out that's already in the queue
                existing_message_history = _empty_update_queue(
                    updates_queue, shutdown_event, is_blocking_allowed=False
                )
                initial_state_dump = convert_agent_messages_to_task_update(
                    new_messages=existing_message_history,
                    task_id=task_id,
                )
                # and let the front end know about the current state
                yield initial_state_dump
                # finally, just keep reading from the queue
                current_task_update = initial_state_dump
                while True:
                    new_messages = _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=True)
                    if len(new_messages) == 0:
                        yield TaskUpdate(
                            task_id=task_id,
                            finished_request_ids=(),
                            chat_messages=(),
                            updated_artifacts=(),
                            in_progress_chat_message=current_task_update.in_progress_chat_message,
                            queued_chat_messages=current_task_update.queued_chat_messages,
                            logs=(),
                            in_progress_user_message_id=current_task_update.in_progress_user_message_id,
                            check_update_messages=(),
                            new_suggestion_messages=(),
                            inserted_messages=(),
                        )
                    else:
                        # and send updates as they come in
                        current_task_update = convert_agent_messages_to_task_update(
                            new_messages=new_messages,
                            task_id=task_id,
                            current_state=current_task_update,
                        )
                        yield current_task_update


def _log_filter_fn(log_dict: dict[str, Any]) -> bool:
    extra_dict = log_dict.get("record", {}).get("extra", {})
    if extra_dict.get("log_type", "") != USER_FACING_LOG_TYPE:
        return False
    return True


@contextmanager
def _observe_new_logs_for_task(
    task_id: TaskID, queue: Queue[TaskUpdateTypes], settings: SculptorSettings
) -> Generator[None, None, None]:
    log_dir = Path(settings.LOG_PATH)
    current_log_file = Path(log_dir) / "tasks" / f"{task_id}.json"

    # now stream all lines in the current log, and any new ones
    stop_event = threading.Event()
    watcher_thread = ObservableThread(
        target=observe_jsonl_log_file,
        args=(current_log_file, queue, lambda x: _log_filter_fn(x), stop_event),
    )
    watcher_thread.start()
    try:
        yield
    finally:
        # Signal thread to stop
        stop_event.set()
        # Wait for thread to finish
        watcher_thread.join(timeout=1.0)
        if watcher_thread.is_alive():
            logger.error("File watcher thread did not shut down in time.")


def create_initial_task_view(task: Task, settings: SculptorSettings) -> TaskViewTypes:
    # For some reason, matching on task.input_data directly makes Pyre fail the exhaustiveness check
    input_data = task.input_data
    match input_data:
        case AgentTaskInputsV1():
            task_view_class = CodingAgentTaskView
        case SendEmailTaskInputsV1():
            task_view_class = SendEmailTaskView
        case CleanupImagesInputsV1():
            task_view_class = CleanupImagesTaskView
        case CacheReposInputsV1():
            task_view_class = CacheReposTaskView
        case _ as unreachable:
            assert_never(unreachable)
    # pyre-ignore[61]: Pyre thinks task_view_class can be undefined, despite the exhaustiveness check above
    instance = task_view_class()
    instance._task_container.append(task)
    instance._settings_container.append(settings)
    return instance


def _empty_update_queue(updates_queue: Queue[T], shutdown_event: Event, is_blocking_allowed: bool) -> list[T]:
    """Empties the queue and returns all items in it."""
    all_data: list[T] = []

    # first get everything that's already in the queue
    while updates_queue.qsize() > 0:
        data = updates_queue.get()
        all_data.append(data)

    # if there was anything at all, we can return it immediately
    if len(all_data) > 0:
        return all_data

    # if we can't block, we're done
    if not is_blocking_allowed:
        return all_data

    # otherwise, if we're allowed to block, we can wait for more data
    start_time = time.monotonic()
    while True:
        try:
            data = updates_queue.get(timeout=_POLL_SECONDS)
        except Empty:
            if shutdown_event.is_set():
                logger.info("Server is stopping, no more updates will be sent.")
                raise ServerStopped("Shutting down because the server is stopping.")
            if time.monotonic() - start_time > _KEEPALIVE_SECONDS:
                return all_data
            else:
                continue
        else:
            # might as well go return the rest of it too
            all_data = [data] + _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=False)
            return all_data

    assert False, "This should never be reached, as we either return or raise an exception in the loop above."


def stream_tasks(
    user_session: UserSession, project_id: ProjectID, shutdown_event: Event, services: CompleteServiceCollection
) -> Generator[TaskListUpdate | None, None, None]:
    # first, subscribe to the task updates
    with services.task_service.subscribe_to_complete_tasks_for_user(
        user_reference=user_session.user_reference, project_id=project_id
    ) as updates_queue:
        updates_queue = cast(Queue[TaskListUpdateTypes], updates_queue)
        # next, subscribe to any data model updates for this task
        with services.data_model_service.observe_user_changes(
            user_reference=user_session.user_reference,
            organization_reference=user_session.organization_reference,
            queue=updates_queue,
        ):
            # read everything out that's already in the queue
            earlier_data = _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=False)
            current_state = _convert_to_task_list_update(TaskListUpdate(), earlier_data, services.settings)
            # and let the front end know about the current state
            yield current_state
            # finally, just keep reading from the queue
            while True:
                new_data = _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=True)
                if len(new_data) == 0:
                    yield current_state
                else:
                    # and send updates as they come in
                    logger.trace("Got new data for task list update: {}", new_data)
                    current_state = _convert_to_task_list_update(current_state, new_data, services.settings)
                    yield current_state


def _convert_to_task_list_update(
    current_state: TaskListUpdate, all_data: list[TaskListUpdateTypes], settings: SculptorSettings
) -> TaskListUpdate:
    """Converts a list of models into a TaskListUpdate."""
    new_messages_by_task_id = {}
    finished_request_ids = []
    for model in all_data:
        match model:
            case TaskMessageContainer():
                coding_agent_task_ids = set()
                for task in model.tasks:
                    if not isinstance(task.input_data, AgentTaskInputsV1):
                        continue
                    task_id_str = str(task.object_id)
                    coding_agent_task_ids.add(task_id_str)
                    if task_id_str not in current_state.task_by_task_id:
                        task_view = create_initial_task_view(task, settings)
                        assert isinstance(task_view, CodingAgentTaskView), (
                            f"should be impossible: {task=} resulted in non-CodingAgentTaskView view {task_view=} "
                        )
                        current_state.task_by_task_id[task_id_str] = task_view
                    current_state.task_by_task_id[task_id_str].update_task(task)
                for message, task_id in model.messages:
                    task_id_str = str(task_id)
                    if task_id_str not in coding_agent_task_ids:
                        continue
                    current_state.task_by_task_id[task_id_str].add_message(message)
                    if not isinstance(message, PartialResponseBlockAgentMessage):
                        if task_id_str not in new_messages_by_task_id:
                            new_messages_by_task_id[task_id_str] = []
                        new_messages_by_task_id[task_id_str].append(message)
            case CompletedTransaction():
                completed_transaction = model
                if completed_transaction.request_id is not None:
                    finished_request_ids.append(completed_transaction.request_id)
            case SculptorSettings():
                # keep the type checker happy
                pass
            case _ as unreachable:
                assert_never(unreachable)
    return TaskListUpdate(
        task_by_task_id=current_state.task_by_task_id,
        finished_request_ids=tuple(finished_request_ids),
    )


class ProjectNotFoundError(ExpectedError):
    pass


class _LocalRepoInfoExfiltrationCallback:
    """
    DONT USE THIS PATTERN.

    This is a stopgap until we implement a proper service-oriented watcher stream in the git repo service
    """

    def __init__(self, services: CompleteServiceCollection, user_ref: UserReference, project_id: ProjectID):
        self.services = services
        self.user_ref = user_ref
        self.project_id = project_id

    def __call__(self) -> LocalRepoInfo | None:
        try:
            with self.open_repo_for_read() as repo:
                # TODO: add a top-level repo health check
                #       as otherwise this will error out without
                #       context to the user, if the repo becomes
                #       invalid
                try:
                    current_branch = repo.get_current_git_branch()
                except FileNotFoundError as e:
                    logger.debug(f"Failed to get current git branch because the repo doesn't exist: {e}")
                    return None
                except GitRepoError as e:
                    if e.branch_name is None:
                        logger.debug(f"There is no current branch: {e}")
                        return None
                    else:
                        raise
                status = repo.get_current_status(is_read_only_and_lockless=True)

                return LocalRepoInfo(
                    status=status,
                    current_branch=current_branch,
                    project_id=self.project_id,
                )
        except Exception as e:
            log_exception(
                e, message="Failed to get user's git repository state", priority=ExceptionPriority.LOW_PRIORITY
            )
            return None

    @contextmanager
    def open_repo_for_read(self) -> Generator[ReadOnlyGitRepo, None, None]:
        with self.services.data_model_service.open_transaction(RequestID()) as transaction:
            project = transaction.get_project(self.project_id)
        if not project:
            raise ProjectNotFoundError(f"Project {self.project_id} not found")
        with self.services.git_repo_service.open_local_user_git_repo_for_read(self.user_ref, project) as repo:
            yield repo


@contextmanager
def stream_repo_info_updates_via_polling(
    poll_for_status_callback: Callable[[], LocalRepoInfo | None], queue: Queue[UserUpdateSourceTypes]
) -> Generator[None, None, None]:
    """
    DONT USE THIS PATTERN.

    This is a stopgap until we implement a proper service-oriented watcher stream in the git repo service
    """
    source = StopGapBackgroundPollingStreamSource(
        polling_callback=poll_for_status_callback,
        output_queue=queue,
        check_interval_in_seconds=_GIT_STATUS_POLL_SECONDS,
    )
    with source.thread_polling_into_queue():
        yield
