import datetime
import shutil
from abc import ABC
from abc import abstractmethod
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import Callable
from typing import Generator
from typing import TypeVar
from typing import cast

from loguru import logger
from pydantic import AnyUrl
from pydantic import PrivateAttr

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.common import is_live_debugging
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.errors import ExpectedError
from sculptor.foundation.event_utils import ShutdownEvent
from sculptor.foundation.nested_evolver import assign
from sculptor.foundation.nested_evolver import chill
from sculptor.foundation.nested_evolver import evolver
from sculptor.foundation.serialization import SerializedException
from sculptor.foundation.time_utils import get_current_time
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentReleasedRunnerMessage
from sculptor.interfaces.agents.agent import EphemeralMessage
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PersistentMessageTypes
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import TaskStatusRunnerMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import FileAgentArtifact
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.interfaces.environments.base import Environment
from sculptor.primitives.constants import MESSAGE_LOG_TYPE
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction
from sculptor.services.data_model_service.sql_implementation import SQLTransaction
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.task_service.api import TaskService
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import InvalidTaskOperation
from sculptor.services.task_service.errors import TaskError
from sculptor.services.task_service.errors import TaskNotFound
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.services.task_service.errors import UserStoppedTaskError
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.state.messages import AgentMessageSource
from sculptor.state.messages import Message
from sculptor.state.messages import ModelOption
from sculptor.state.messages import PersistentMessage
from sculptor.tasks.api import run_task
from sculptor.utils.errors import is_irrecoverable_exception
from sculptor.utils.filtered_queue import FilteredQueue

_RegistryKeyT = TypeVar("_RegistryKeyT")


class BaseTaskService(TaskService, ABC):
    """The DefaultTaskService exists to broker requests for tasks running."""

    settings: SculptorSettings
    data_model_service: TaskDataModelService
    dependency_management_service: DependencyManagementService
    git_repo_service: GitRepoService
    project_service: ProjectService
    workspace_service: WorkspaceService

    _completion_deadline: dict[TaskID, datetime.datetime] = PrivateAttr(default_factory=dict)
    _subscriptions_by_task_id: dict[TaskID, list[Queue[Message]]] = PrivateAttr(default_factory=dict)
    _subscriptions_by_user_reference: dict[UserReference, list[Queue[TaskMessageContainer]]] = PrivateAttr(
        default_factory=dict
    )
    _subscriptions_by_project_id: dict[ProjectID, list[Queue[TaskMessageContainer]]] = PrivateAttr(
        default_factory=dict
    )
    _subscriptions_by_workspace_id_for_containers: dict[WorkspaceID, list[Queue[TaskMessageContainer]]] = PrivateAttr(
        default_factory=dict
    )
    _subscriptions_by_task_id_for_containers: dict[TaskID, list[Queue[TaskMessageContainer]]] = PrivateAttr(
        default_factory=dict
    )
    # this is important for robustness -- we want to ensure that no messages are missed when starting a subscription
    _subscription_lock: Lock = PrivateAttr(default_factory=Lock)
    _messages_by_task_id: dict[TaskID, list[Message]] = PrivateAttr(default_factory=dict)
    _latest_task_by_task_id: dict[TaskID, Task] = PrivateAttr(default_factory=dict)
    _task_ids_pending_creation: set[TaskID] = PrivateAttr(default_factory=set)

    _shutdown_flag: ShutdownEvent = PrivateAttr(default_factory=ShutdownEvent.build_root)
    _shutdown_flag_by_task_id: dict[TaskID, ShutdownEvent] = PrivateAttr(default_factory=dict)

    def start(self) -> None:
        super().start()
        self._finalize_recently_deleted_tasks()
        with self.data_model_service.open_task_transaction() as transaction:
            tasks = transaction.get_active_tasks()
            all_messages = transaction.get_messages_for_tasks([task.object_id for task in tasks])
            for task in tasks:
                saved_messages = all_messages.get(task.object_id, ())
                self._messages_by_task_id[task.object_id] = [saved_message.message for saved_message in saved_messages]
                self._latest_task_by_task_id[task.object_id] = task

    @abstractmethod
    def on_new_task(self, task: Task) -> None:
        if task.object_id in self._task_ids_pending_creation:
            self._task_ids_pending_creation.remove(task.object_id)

    @abstractmethod
    def on_restore_task(self, task: Task) -> None:
        raise NotImplementedError()

    def create_task(self, task: Task, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        upserted_task = transaction.upsert_task(task)
        message = TaskStatusRunnerMessage(outcome=TaskState.QUEUED, message_id=AgentMessageID())
        self.create_message(message, upserted_task.object_id, transaction)
        self._task_ids_pending_creation.add(upserted_task.object_id)
        transaction.add_callback(lambda: self.on_new_task(task=upserted_task))
        return upserted_task

    def create_message(self, message: MessageTypes, task_id: TaskID, transaction: DataModelTransaction) -> None:
        assert isinstance(transaction, SQLTransaction)
        task_row = transaction.get_task(task_id)
        assert task_row is not None
        if isinstance(message, EphemeralMessage):
            transaction.add_callback(lambda: self._publish_task_update(task=task_row, message=message))
        else:
            assert isinstance(message, PersistentMessage)
            saved_message = SavedAgentMessage.build(message=message, task_id=task_id)
            transaction.insert_message(saved_message)
            transaction.add_callback(lambda: self._publish_task_update(task=task_row, message=message))

    def get_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task | None:
        assert isinstance(transaction, SQLTransaction)
        return transaction.get_task(task_id)

    # TODO(SCU-135): Remove this method when git/diff operations move to workspace level.
    # The EnvironmentAcquiredRunnerMessage.environment field and this accessor will be
    # replaced by workspace-level API endpoints.
    def get_task_environment(self, task_id: TaskID, transaction: DataModelTransaction) -> Environment | None:
        """Get the active environment for a task by checking message history.

        Scans the task's in-memory messages for the most recent EnvironmentAcquiredRunnerMessage
        that hasn't been followed by an EnvironmentReleasedRunnerMessage.
        Returns None if no environment is currently active.

        Note: Uses the in-memory message cache via _subscribe_to_task because
        EnvironmentAcquiredRunnerMessage is ephemeral and not persisted to the database.
        """
        assert isinstance(transaction, SQLTransaction)

        # Use _subscribe_to_task to access the in-memory message history
        with self._subscribe_to_task(
            task_id, lambda m: m.source == AgentMessageSource.RUNNER, is_history_included=True
        ) as listener:
            # Iterate in reverse to find the most recent state
            for message in reversed(list(listener.queue)):
                # If a released message arrived after all acquired messages, there is no environment
                if isinstance(message, EnvironmentReleasedRunnerMessage):
                    return None
                # Otherwise, return the most recently acquired environment
                if isinstance(message, EnvironmentAcquiredRunnerMessage):
                    return message.environment

        return None

    def _check_workspace_not_deleted(self, task: Task, transaction: DataModelTransaction) -> None:
        """Raise InvalidTaskOperation if the task's workspace has been deleted."""
        if not isinstance(task.current_state, AgentTaskStateV2):
            return
        workspace = transaction.get_workspace_include_deleted(task.current_state.workspace_id)
        if workspace is None or workspace.is_deleted:
            raise InvalidTaskOperation("Cannot restore task: its workspace has been deleted")

    def mark_read(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        logger.debug("Marking task {} as read", task_id)
        updated_task = task.evolve(task.ref().last_read_at, get_current_time())
        updated_task = transaction.upsert_task(updated_task)
        transaction.add_callback(lambda: self._publish_task_update(task=updated_task))
        return updated_task

    def mark_unread(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        logger.debug("Marking task {} as unread", task_id)
        updated_task = task.evolve(task.ref().last_read_at, None)
        updated_task = transaction.upsert_task(updated_task)
        transaction.add_callback(lambda: self._publish_task_update(task=updated_task))
        return updated_task

    def update_available_models(
        self,
        task_id: TaskID,
        available_models: Sequence[ModelOption],
        current_model: ModelOption | None,
        transaction: DataModelTransaction,
    ) -> Task | None:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if task is None or not isinstance(task.current_state, AgentTaskStateV2):
            return None
        models = list(available_models)
        state = task.current_state
        if state.available_models == models and state.current_model == current_model:
            return None
        # Evolve only the catalog fields; the title is read from this same task
        # row, so a concurrent rename already committed is preserved.
        mutable_state = evolver(state)
        assign(mutable_state.available_models, lambda: models)
        assign(mutable_state.current_model, lambda: current_model)
        updated_task = task.evolve(task.ref().current_state, chill(mutable_state).model_dump())
        updated_task = transaction.upsert_task(updated_task)
        # Publish the same task-update a message write registers, so a live
        # switcher refreshes even though this change created no message.
        transaction.add_callback(lambda: self._publish_task_update(task=updated_task))
        return updated_task

    def restore_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        if task.outcome != TaskState.FAILED:
            raise InvalidTaskOperation("Task is not in a failed state - cannot restore")
        self._check_workspace_not_deleted(task, transaction)
        updated_task = task.evolve(task.ref().outcome, TaskState.QUEUED)
        updated_task = transaction.upsert_task(updated_task)
        message = TaskStatusRunnerMessage(outcome=TaskState.QUEUED, message_id=AgentMessageID())
        self.create_message(message=message, task_id=updated_task.object_id, transaction=transaction)
        transaction.add_callback(lambda: self.on_restore_task(task=updated_task))
        return updated_task

    def delete_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        if task.is_deleted:
            return
        if task.outcome == TaskState.RUNNING:
            # Task has an active runner — use cooperative shutdown via is_deleting flag.
            # The runner will finalize the deletion when it observes the flag.
            updated_task = task.evolve(task.ref().is_deleting, True)
            updated_task = transaction.upsert_task(updated_task)
            shutdown_event = self._shutdown_flag_by_task_id.get(task_id)
            if shutdown_event is not None:
                shutdown_event.set()
            transaction.add_callback(lambda: self._publish_task_update(task=updated_task))
        else:
            # Task is idle (no runner) — finalize immediately to avoid getting stuck
            # in is_deleting with nothing to complete the transition.
            self._finalize_task_as_deleted(task, transaction)

    def get_artifact_file_url(self, task_id: TaskID, artifact_name: str) -> AnyUrl:
        output_path = self._get_task_output_path(task_id)
        return AnyUrl(
            f"file://{output_path / artifact_name}",
        )

    def set_artifact_file_data(self, task_id: TaskID, artifact_name: str, artifact_data: str | bytes) -> None:
        artifact_path = self._get_task_output_path(task_id) / artifact_name
        logger.debug("writing artifact data to {}", artifact_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(artifact_data, str):
            artifact_path.write_text(artifact_data)
        else:
            artifact_path.write_bytes(artifact_data)

    def ensure_artifact_cache_populated(self, task_id: TaskID, artifact_name: str) -> bool:
        """Make the cached artifact file for (task_id, artifact_name) readable, or return False.

        Returns True if {task_sync_dir}/{task_id}/{artifact_name} exists after this
        call. If the cache file is missing — e.g. because the cache was wiped or
        the task was last touched before the cache existed — looks for the most
        recent per-emit snapshot in the workspace's stable artifacts dir
        ({workspace_root}/artifacts/tasks/{task_id}/{artifact_name}-*) and copies
        it into the cache so subsequent reads succeed via the normal path.

        This is the SCU-1245 backfill path. Both _build_existing_artifact_messages
        and the web layer's _get_artifact_data go through this before deciding
        the artifact is gone, so a wiped cache no longer empties the UI as long
        as the source-of-truth files in the workspace artifacts dir are intact.
        """
        cache_path = self._get_task_output_path(task_id) / artifact_name
        if cache_path.exists():
            return True
        snapshot = self._find_latest_workspace_artifact_snapshot(task_id, artifact_name)
        if snapshot is None:
            return False
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot, cache_path)
        except OSError as e:
            # Backfill is best-effort; if the copy fails (disk full, permissions),
            # the caller treats this as "no artifact" and skips. Debug-level since
            # it's recoverable on the next successful agent emit.
            logger.debug("Failed to backfill artifact cache from {} to {}: {}", snapshot, cache_path, e)
            return False
        logger.debug("Backfilled {} artifact for task {} from {}", artifact_name, task_id, snapshot)
        return True

    def _find_latest_workspace_artifact_snapshot(self, task_id: TaskID, artifact_name: str) -> Path | None:
        task = self._latest_task_by_task_id.get(task_id)
        if task is None or not isinstance(task.current_state, AgentTaskStateV2):
            return None
        persistent_dir = self.workspace_service.get_persistent_task_artifacts_dir(
            task.current_state.workspace_id, task_id
        )
        if persistent_dir is None or not persistent_dir.exists():
            return None
        # Per-emit files are named "{artifact_name}-{uuid}" (see _make_file_artifact).
        candidates = list(persistent_dir.glob(f"{artifact_name}-*"))
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _get_task_output_path(self, task_id: TaskID) -> Path:
        sync_dir = self.task_sync_dir / str(task_id)
        return sync_dir.absolute()

    def get_saved_messages_for_task(
        self, task_id: TaskID, transaction: DataModelTransaction
    ) -> tuple[PersistentMessageTypes, ...]:
        assert isinstance(transaction, SQLTransaction)
        return tuple(x.message for x in transaction.get_messages_for_task(task_id))

    def get_live_messages_for_task(self, task_id: TaskID) -> tuple[Message, ...]:
        # Same lock as create_message's append so the snapshot is consistent.
        with self._subscription_lock:
            return tuple(self._messages_by_task_id.get(task_id, ()))

    @contextmanager
    def subscribe_to_all_tasks_for_user(
        self, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        # filter down to just the particular types that are needed here
        listener: Queue[TaskMessageContainer] = FilteredQueue(
            lambda x: not isinstance(x, PartialResponseBlockAgentMessage)
        )
        with self._subscription_lock:
            self._subscriptions_by_user_reference.setdefault(user_reference, []).append(listener)
            # we must query the existing messages for this task inside the lock
            # otherwise there is a race condition where the listener might not see some messages that are being committed
            # or they might arrive out of order (both of which are bad)
            with self.data_model_service.open_transaction(RequestID()) as transaction:
                # pyrefly: ignore [missing-attribute]
                tasks = transaction.get_tasks_for_user(user_reference)
                task_ids = {task.object_id for task in tasks}
            latest_tasks = tuple(
                self._latest_task_by_task_id[task_id]
                for task_id in task_ids
                if task_id in self._latest_task_by_task_id
            )
            messages_and_task_ids = tuple(
                (message, task_id) for task_id in task_ids for message in self._messages_by_task_id.get(task_id, [])
            )

            # Ephemeral artifact notifications are lost across restarts because they
            # are not persisted to the DB.  Check which tasks have artifact files on
            # disk and inject synthetic UpdatedArtifactAgentMessage entries so the
            # frontend learns about them in the initial state dump.
            artifact_messages = self._build_existing_artifact_messages(task_ids)

        task_message = TaskMessageContainer(
            tasks=latest_tasks,
            messages=messages_and_task_ids + artifact_messages,
        )
        listener.put_nowait(task_message)

        yield listener

        with self._subscription_lock:
            listeners = self._subscriptions_by_user_reference[user_reference]
            listeners.remove(listener)
            if not listeners:
                del self._subscriptions_by_user_reference[user_reference]

    @contextmanager
    def subscribe_to_project_task_containers(
        self, project_id: ProjectID, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        with self._scoped_task_container_subscription(
            user_reference=user_reference,
            registry=self._subscriptions_by_project_id,
            registry_key=project_id,
            task_filter=lambda t: t.project_id == project_id,
        ) as listener:
            yield listener

    @contextmanager
    def subscribe_to_workspace_task_containers(
        self, workspace_id: WorkspaceID, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        with self._scoped_task_container_subscription(
            user_reference=user_reference,
            registry=self._subscriptions_by_workspace_id_for_containers,
            registry_key=workspace_id,
            task_filter=lambda t: (
                isinstance(t.current_state, AgentTaskStateV2) and t.current_state.workspace_id == workspace_id
            ),
        ) as listener:
            yield listener

    @contextmanager
    def subscribe_to_single_task_container(
        self, task_id: TaskID, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        with self._scoped_task_container_subscription(
            user_reference=user_reference,
            registry=self._subscriptions_by_task_id_for_containers,
            registry_key=task_id,
            task_filter=lambda t: t.object_id == task_id,
        ) as listener:
            yield listener

    @contextmanager
    def _scoped_task_container_subscription(
        self,
        user_reference: UserReference,
        registry: dict[_RegistryKeyT, list[Queue[TaskMessageContainer]]],
        registry_key: _RegistryKeyT,
        task_filter: Callable[[Task], bool],
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        listener: Queue[TaskMessageContainer] = FilteredQueue(
            lambda x: not isinstance(x, PartialResponseBlockAgentMessage)
        )
        with self._subscription_lock:
            registry.setdefault(registry_key, []).append(listener)
            with self.data_model_service.open_transaction(RequestID()) as transaction:
                # pyrefly: ignore [missing-attribute]
                tasks = transaction.get_tasks_for_user(user_reference)
                matching_task_ids = {task.object_id for task in tasks if task_filter(task)}
            latest_tasks = tuple(
                self._latest_task_by_task_id[task_id]
                for task_id in matching_task_ids
                if task_id in self._latest_task_by_task_id
            )
            messages_and_task_ids = tuple(
                (message, task_id)
                for task_id in matching_task_ids
                for message in self._messages_by_task_id.get(task_id, [])
            )
            artifact_messages = self._build_existing_artifact_messages(matching_task_ids)

        listener.put_nowait(
            TaskMessageContainer(
                tasks=latest_tasks,
                messages=messages_and_task_ids + artifact_messages,
            )
        )

        yield listener

        with self._subscription_lock:
            listeners = registry[registry_key]
            listeners.remove(listener)
            if not listeners:
                del registry[registry_key]

    def _build_existing_artifact_messages(
        self, task_ids: set[TaskID]
    ) -> tuple[tuple[UpdatedArtifactAgentMessage, TaskID], ...]:
        """Build synthetic artifact notifications for artifacts that exist on disk.

        Ephemeral UpdatedArtifactAgentMessage notifications are not persisted to
        the database, so they are lost across restarts.  This method checks for
        artifact files on disk and creates notifications so the frontend can
        fetch them via the normal flow.
        """
        result: list[tuple[UpdatedArtifactAgentMessage, TaskID]] = []
        for task_id in task_ids:
            for artifact_type in (ArtifactType.PLAN,):
                # ensure_artifact_cache_populated returns False if neither the
                # cache nor a workspace-side snapshot is available, which is the
                # legitimate "no artifact ever emitted" case — skip silently.
                if not self.ensure_artifact_cache_populated(task_id, artifact_type):
                    continue
                artifact_url = self.get_artifact_file_url(task_id, artifact_type)
                logger.debug("Injecting existing {} artifact notification for task {}", artifact_type, task_id)
                message = UpdatedArtifactAgentMessage(
                    message_id=AgentMessageID(),
                    artifact=FileAgentArtifact(
                        name=artifact_type,
                        url=artifact_url,
                    ),
                )
                result.append((message, task_id))
        return tuple(result)

    @contextmanager
    def subscribe_to_task(self, task_id: TaskID) -> Generator[Queue[Message], None, None]:
        with self._subscribe_to_task(task_id, filter_fn=None) as listener:
            yield listener

    @contextmanager
    def subscribe_to_user_and_sculptor_system_messages(
        self, task_id: TaskID
    ) -> Generator[Queue[UserMessageUnion | ResumeAgentResponseRunnerMessage], None, None]:
        filter_fn = lambda x: x.source in (AgentMessageSource.USER, AgentMessageSource.SCULPTOR_SYSTEM)  # noqa: E731
        with self._subscribe_to_task(task_id, filter_fn) as listener:
            # by message_types_test::test_all_user_message_types_are_in_union and message_types_test::test_all_system_message_types_are_in_union,
            # we know that the listener is a queue of UserMessageUnion.
            # (we must cast rather than assert because we've got parameterized generics)
            yield cast(Queue[UserMessageUnion | ResumeAgentResponseRunnerMessage], listener)

    def _publish_task_update(self, task: Task, message: Message | None = None) -> None:
        """
        Publishes
            - an updated task together with an optional message to all user-scope listeners.
            - if provided, the message to all task-specific listeners.

        """
        task_id = task.object_id
        logger.trace("Publishing task for task {} ({})", task_id, message or "(no message)")
        with self._subscription_lock:
            if message is not None:
                logger.bind(
                    log_type=MESSAGE_LOG_TYPE, task_id=str(task_id), serialized_message=message.model_dump_json()
                ).trace("Published new message to task listeners")
                if task_id not in self._messages_by_task_id:
                    self._messages_by_task_id[task_id] = []
                self._messages_by_task_id[task_id].append(message)

                listeners = self._subscriptions_by_task_id.get(task_id, ())
                for listener in listeners:
                    listener.put_nowait(message)

            # also publish to the overall listeners
            messages = () if message is None else ((message, task_id),)
            task_update = TaskMessageContainer(tasks=(task,), messages=messages)
            self._latest_task_by_task_id[task_id] = task

            user_listeners = self._subscriptions_by_user_reference.get(task.user_reference, ())
            for listener in user_listeners:
                listener.put_nowait(task_update)

            for listener in self._subscriptions_by_project_id.get(task.project_id, ()):
                listener.put_nowait(task_update)

            if isinstance(task.current_state, AgentTaskStateV2):
                workspace_listeners = self._subscriptions_by_workspace_id_for_containers.get(
                    task.current_state.workspace_id, ()
                )
                for listener in workspace_listeners:
                    listener.put_nowait(task_update)

            for listener in self._subscriptions_by_task_id_for_containers.get(task_id, ()):
                listener.put_nowait(task_update)

    @contextmanager
    def _subscribe_to_task(
        self,
        task_id: TaskID,
        filter_fn: Callable[[Message], bool] | None,
        is_history_included: bool = True,
    ) -> Generator[Queue[Message], None, None]:
        listener: Queue[Message] = FilteredQueue(filter_fn) if filter_fn else Queue()
        with self._subscription_lock:
            existing_listeners = self._subscriptions_by_task_id.setdefault(task_id, [])
            existing_listeners.append(listener)
            # we must query the existing messages for this task inside the lock
            # otherwise there is a race condition where the listener might not see some messages that are being committed
            # or they might arrive out of order (both of which are bad)
            messages = self._messages_by_task_id.get(task_id, [])

        # we make sure that any existing messages are here, thus the subscriber will get all messages
        if is_history_included:
            for message in messages:
                listener.put_nowait(message)

        yield listener

        with self._subscription_lock:
            listeners = self._subscriptions_by_task_id[task_id]
            listeners.remove(listener)
            if not listeners:
                del self._subscriptions_by_task_id[task_id]

    def _get_services_for_task(self) -> ServiceCollectionForTask:
        return ServiceCollectionForTask(
            settings=self.settings,
            task_service=self,
            data_model_service=self.data_model_service,
            dependency_management_service=self.dependency_management_service,
            git_repo_service=self.git_repo_service,
            project_service=self.project_service,
            workspace_service=self.workspace_service,
        )

    def _run_task(
        self,
        task: Task,
        services: ServiceCollectionForTask,
        settings: SculptorSettings,
        concurrency_group: ConcurrencyGroup,
    ) -> None:
        try:
            with logger.contextualize(task_id=task.object_id):
                logger.debug("Running task {} {}", task.__class__.__name__, task.object_id)
                assert task.outcome == TaskState.RUNNING

                # We hold on to the error to publish in the except branches below, so
                # that we can handle them correctly in the finalization transaction.
                error_to_publish: SerializedException | None = None

                # if possible, set this even if there was an exception so that we know what happened
                outcome: TaskState | None = None

                # make a note of when the task should be completed by (if any)
                max_seconds = task.max_seconds
                if max_seconds is None:
                    deadline = None
                else:
                    deadline = get_current_time() + timedelta(seconds=max_seconds)
                    self._completion_deadline[task.object_id] = deadline

                maybe_transaction_callback = None
                is_user_notified = False
                shutdown_flag = ShutdownEvent.from_parent(self._shutdown_flag)
                self._shutdown_flag_by_task_id[task.object_id] = shutdown_flag
                try:
                    maybe_transaction_callback = run_task(
                        task=task,
                        services=services,
                        task_deadline=deadline,
                        settings=settings,
                        concurrency_group=concurrency_group,
                        shutdown_event=shutdown_flag,
                    )
                    outcome = TaskState.SUCCEEDED
                    logger.debug("Finished running task {}", task.object_id)

                except UserPausedTaskError:
                    with self.data_model_service.open_task_transaction() as transaction:
                        gotten_task = transaction.get_task(task.object_id)
                        assert gotten_task is not None
                        task = gotten_task
                        if task.is_deleting:
                            outcome = TaskState.DELETED
                        else:
                            outcome = TaskState.QUEUED

                except UserStoppedTaskError:
                    outcome = TaskState.CANCELLED

                except Exception as e:
                    outcome = TaskState.FAILED

                    if isinstance(e, TaskError):
                        # task errors are already logged inside of run_task, so we should not log them again
                        maybe_transaction_callback = e.transaction_callback
                        is_user_notified = e.is_user_notified
                    else:
                        if isinstance(e, ExpectedError):
                            log_exception(
                                exc=e,
                                message="Task execution failed with expected error",
                                priority=ExceptionPriority.LOW_PRIORITY,
                            )
                        else:
                            log_exception(
                                exc=e,
                                message="Task execution failed with unexpected error",
                                priority=ExceptionPriority.MEDIUM_PRIORITY,
                            )

                    serialized_exception = SerializedException.build(e)
                    error_to_publish = serialized_exception

                    if is_live_debugging() or is_irrecoverable_exception(e):
                        raise

                except BaseException as e:
                    # we want to make sure that we log unexpected exceptions to sentry
                    # we will *also* log it in the task service handler, but it will be marked here as already handled
                    # so that we don't log it twice
                    log_exception(e, "Task execution failed unexpectedly", priority=ExceptionPriority.HIGH_PRIORITY)
                    outcome = TaskState.FAILED
                    error_to_publish = SerializedException.build(e)
                    raise

                finally:
                    self._finalize_task(task, outcome, error_to_publish, maybe_transaction_callback, is_user_notified)
        except BaseException as e:
            # we will avoid duplicate logging of the exceptions due to the EXCEPTION_LOGGED_FLAG,
            # but we do want to be sure to capture any failures (since this is run in a bare asyncio task)
            log_exception(e, "Task processing failed unexpectedly", priority=ExceptionPriority.HIGH_PRIORITY)
            raise

    def _finalize_task(
        self,
        task: Task,
        outcome: TaskState | None,
        error_to_publish: SerializedException | None,
        maybe_transaction_callback: Callable[[DataModelTransaction], None] | None,
        is_user_notified: bool,
    ) -> None:
        task_id = task.object_id

        # finalize task here if it wasn't already finalized
        with self.data_model_service.open_task_transaction() as transaction:
            if outcome == TaskState.DELETED:
                gotten_task = transaction.get_task(task_id)
                assert gotten_task is not None
                self._finalize_task_as_deleted(gotten_task, transaction)
                return

            # add any requested data model updates to this transaction
            if maybe_transaction_callback is not None:
                maybe_transaction_callback(transaction)

            # then go make sure we've updated the task outcome
            logged_task = transaction.get_task(task_id)
            assert logged_task is not None

            # If the task was marked for deletion while running, finalize as DELETED.
            # NOTE: Even if this check sees a stale is_deleting=False (due to SQLite
            # snapshot isolation), the monotonic trigger on task_latest will prevent
            # the upsert below from overwriting a committed is_deleting=True.
            if logged_task.is_deleting:
                self._finalize_task_as_deleted(logged_task, transaction)
                return

            if logged_task.outcome == TaskState.CANCELLED:
                # if the task was cancelled, we don't want to update the outcome
                pass
            elif logged_task.outcome != outcome:
                task_with_new_outcome = logged_task.evolve(logged_task.ref().outcome, outcome)
                if error_to_publish is not None:
                    task_with_new_outcome = task_with_new_outcome.evolve(
                        task_with_new_outcome.ref().error, error_to_publish
                    )
                transaction.upsert_task(task_with_new_outcome)

            assert outcome is not None
            final_update_message = TaskStatusRunnerMessage(outcome=outcome, message_id=AgentMessageID())
            self.create_message(final_update_message, task.object_id, transaction)

    def _finalize_task_as_deleted(self, task: Task, transaction: TaskAndDataModelTransaction) -> None:
        """Mark a task as fully deleted, clean up its caches and log file."""
        new_task = task.evolve(task.ref().outcome, TaskState.DELETED)
        new_task = new_task.evolve(new_task.ref().is_deleted, True)
        new_task = new_task.evolve(new_task.ref().is_deleting, False)
        transaction.upsert_task(new_task)
        task_id = task.object_id
        # Publish before cleanup: any live subscriber (notably scope=agent
        # WebSocket connections) needs to observe is_deleted=True so it can
        # close the stream — otherwise --follow hangs after the task dies.
        # Cleanup must run after the publish so the post-publish cache state
        # doesn't retain the just-deleted task.
        transaction.add_callback(lambda: self._publish_task_update(task=new_task))
        transaction.add_callback(lambda: self._cleanup_task_caches(task_id))
        task_log_path = Path(self.settings.LOG_PATH) / "tasks" / f"{task_id}.json"
        task_log_path.unlink(missing_ok=True)

    def _cleanup_task_caches(self, task_id: TaskID) -> None:
        with self._subscription_lock:
            self._messages_by_task_id.pop(task_id, None)
            self._latest_task_by_task_id.pop(task_id, None)
            self._shutdown_flag_by_task_id.pop(task_id, None)

    def _finalize_recently_deleted_tasks(self) -> None:
        with self.data_model_service.open_task_transaction() as transaction:
            to_delete = transaction.get_stuck_deleting_tasks()
        for task in to_delete:
            self._finalize_task(task, TaskState.DELETED, None, None, False)
