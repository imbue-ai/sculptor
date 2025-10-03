import datetime
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import Callable
from typing import Generator

from loguru import logger
from pydantic import AnyUrl
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import is_live_debugging
from imbue_core.constants import ExceptionPriority
from imbue_core.errors import ExpectedError
from imbue_core.sculptor.state.messages import AgentMessageSource
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import PersistentMessage
from imbue_core.serialization import SerializedException
from imbue_core.time_utils import get_current_time
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import NotificationImportance
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import EnvironmentCreatedRunnerMessage
from sculptor.interfaces.agents.v1.agent import EnvironmentStoppedRunnerMessage
from sculptor.interfaces.agents.v1.agent import EphemeralMessage
from sculptor.interfaces.agents.v1.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.v1.agent import PersistentMessageTypes
from sculptor.interfaces.agents.v1.agent import StopAgentUserMessage
from sculptor.interfaces.agents.v1.agent import TaskLifecycleAction
from sculptor.interfaces.agents.v1.agent import TaskLifecycleRunnerMessage
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.interfaces.agents.v1.agent import TaskStatusRunnerMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.primitives.constants import MESSAGE_LOG_TYPE
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.data_model_service.sql_implementation import SQLTransaction
from sculptor.services.environment_service.api import EnvironmentService
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.secrets_service.api import SecretsService
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.task_service.api import TaskService
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import InvalidTaskOperation
from sculptor.services.task_service.errors import TaskError
from sculptor.services.task_service.errors import TaskNotFound
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.services.task_service.errors import UserStoppedTaskError
from sculptor.tasks.api import run_task
from sculptor.utils.errors import is_irrecoverable_exception
from sculptor.utils.filtered_queue import FilteredQueue


class TaskCancelledError(Exception):
    pass


class BaseTaskService(TaskService, ABC):
    """The DefaultTaskService exists to broker requests for tasks running."""

    settings: SculptorSettings
    environment_service: EnvironmentService
    data_model_service: TaskDataModelService
    secrets_service: SecretsService
    anthropic_credentials_service: AnthropicCredentialsService
    git_repo_service: GitRepoService
    project_service: ProjectService

    _completion_deadline: dict[TaskID, datetime.datetime] = PrivateAttr(default_factory=dict)
    _subscriptions_by_task_id: dict[TaskID, list[Queue[Message]]] = PrivateAttr(default_factory=dict)
    _subscriptions_by_user_reference: dict[UserReference, list[Queue[TaskMessageContainer]]] = PrivateAttr(
        default_factory=dict
    )
    # this is important for robustness -- we want to ensure that no messages are missed when starting a subscription
    _subscription_lock: Lock = PrivateAttr(default_factory=Lock)
    _messages_by_task_id: dict[TaskID, list[Message]] = PrivateAttr(default_factory=dict)
    _latest_task_by_task_id: dict[TaskID, Task] = PrivateAttr(default_factory=dict)

    def start(self) -> None:
        super().start()
        with self.data_model_service.open_transaction(RequestID()) as transaction:
            tasks = transaction.get_active_tasks()
            for task in tasks:
                saved_messages = transaction.get_messages_for_task(task.object_id)
                self._messages_by_task_id[task.object_id] = [saved_message.message for saved_message in saved_messages]
                self._latest_task_by_task_id[task.object_id] = task

    @abstractmethod
    def on_new_task(self, task: Task) -> None:
        raise NotImplementedError()

    def create_task(self, task: Task, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        upserted_task = transaction.upsert_task(task)
        message = TaskStatusRunnerMessage(outcome=TaskState.QUEUED, message_id=AgentMessageID())
        self.create_message(message, upserted_task.object_id, transaction)
        transaction.add_callback(lambda: self.on_new_task(task=upserted_task))
        return upserted_task

    def create_message(self, message: Message, task_id: TaskID, transaction: DataModelTransaction) -> None:
        assert isinstance(transaction, SQLTransaction)
        task_row = transaction.get_task(task_id)
        assert task_row is not None
        if isinstance(message, EphemeralMessage):
            transaction.add_callback(lambda: self.publish_task_update(task=task_row, update=message))
        else:
            assert isinstance(message, PersistentMessage)
            saved_message = SavedAgentMessage.build(message=message, task_id=task_id)
            transaction.insert_message(saved_message)
            transaction.add_callback(lambda: self.publish_task_update(task=task_row, update=message))

    def get_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task | None:
        assert isinstance(transaction, SQLTransaction)
        return transaction.get_task(task_id)

    def get_task_environment(self, task_id: TaskID, transaction: DataModelTransaction) -> Environment | None:
        assert isinstance(transaction, SQLTransaction)
        with self._subscribe_to_task(task_id, lambda x: x.source in (AgentMessageSource.RUNNER)) as listener:
            for message in reversed(listener.queue):
                # If a destroyed message arrived after all created messages, there is no
                # environment, so we return None.
                if isinstance(message, EnvironmentStoppedRunnerMessage):
                    return None
                # Otherwise, return the most recently created environment.
                if isinstance(message, EnvironmentCreatedRunnerMessage):
                    return message.environment

        return None

    def set_archived(self, task_id: TaskID, is_archived: bool, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        logger.info("Setting task {} archived status to {}", task_id, is_archived)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        if task.is_archived == is_archived:
            return task
        updated_task = task.evolve(task.ref().is_archived, is_archived)
        updated_task = transaction.upsert_task(updated_task)

        action = TaskLifecycleAction.ARCHIVED if is_archived else TaskLifecycleAction.UNARCHIVED
        lifecycle_message = TaskLifecycleRunnerMessage(action=action)
        transaction.add_callback(lambda: self.publish_task_update(task=updated_task, update=lifecycle_message))

        return updated_task

    def restore_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        if task.outcome != TaskState.FAILED:
            raise InvalidTaskOperation("Task is not in a failed state - cannot restore")
        updated_task = task.evolve(task.ref().outcome, TaskState.QUEUED)
        updated_task = transaction.upsert_task(updated_task)
        message = TaskStatusRunnerMessage(outcome=TaskState.QUEUED, message_id=AgentMessageID())
        self.create_message(message=message, task_id=updated_task.object_id, transaction=transaction)
        transaction.add_callback(lambda: self.publish_task_update(task=updated_task, update=message))
        return updated_task

    def delete_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None:
        assert isinstance(transaction, SQLTransaction)
        task = self.get_task(task_id, transaction)
        if not task:
            raise TaskNotFound(f"{task_id} not found")
        if task.is_deleted:
            return
        updated_task = task.evolve(task.ref().is_deleting, True)
        updated_task = transaction.upsert_task(updated_task)
        message = StopAgentUserMessage(message_id=AgentMessageID())
        self.create_message(message, task_id, transaction)
        transaction.add_callback(lambda: self.publish_task_update(task=updated_task, update=message))

    def get_artifact_file_url(self, task_id: TaskID, artifact_name: str) -> AnyUrl:
        output_path = self._get_task_output_path(task_id)
        return AnyUrl(
            f"file://{output_path / artifact_name}",
        )

    def set_artifact_file_data(self, task_id: TaskID, artifact_name: str, artifact_data: str | bytes) -> None:
        artifact_path = self._get_task_output_path(task_id) / artifact_name
        logger.debug("writing artifact data to {}", artifact_path)
        logger.trace("artifact data for {}:\n{}", artifact_path, artifact_data)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(artifact_data, str):
            artifact_path.write_text(artifact_data)
        else:
            artifact_path.write_bytes(artifact_data)

    def _get_task_output_path(self, task_id: TaskID) -> Path:
        sync_dir = self.task_sync_dir / str(task_id)
        return sync_dir.absolute()

    def get_saved_messages_for_task(
        self, task_id: TaskID, transaction: DataModelTransaction
    ) -> tuple[PersistentMessageTypes, ...]:
        assert isinstance(transaction, SQLTransaction)
        return tuple(x.message for x in transaction.get_messages_for_task(task_id))

    @contextmanager
    def subscribe_to_complete_tasks_for_user(
        self, user_reference: UserReference, project_id: ProjectID
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
                tasks = transaction.get_latest_tasks_for_user(user_reference, project_id)
                task_ids = {task.object_id for task in tasks}
            latest_tasks = tuple(
                self._latest_task_by_task_id[task_id]
                for task_id in task_ids
                if task_id in self._latest_task_by_task_id
            )
            messages_and_task_ids = tuple(
                (message, task_id) for task_id in task_ids for message in self._messages_by_task_id.get(task_id, [])
            )
        task_message = TaskMessageContainer(
            tasks=latest_tasks,
            messages=messages_and_task_ids,
        )
        listener.put_nowait(task_message)

        yield listener

        with self._subscription_lock:
            listeners = self._subscriptions_by_user_reference[user_reference]
            listeners.remove(listener)
            if not listeners:
                del self._subscriptions_by_user_reference[user_reference]

    @contextmanager
    def subscribe_to_task(self, task_id: TaskID) -> Generator[Queue[Message], None, None]:
        with self._subscribe_to_task(task_id, filter_fn=None) as listener:
            yield listener

    @contextmanager
    def subscribe_to_user_and_sculptor_system_messages(self, task_id: TaskID) -> Generator[Queue[Message], None, None]:
        filter_fn = lambda x: x.source in (AgentMessageSource.USER, AgentMessageSource.SCULPTOR_SYSTEM)
        with self._subscribe_to_task(task_id, filter_fn) as listener:
            yield listener

    def publish_task_update(self, task: Task, update: Message) -> None:
        task_id = task.object_id
        logger.trace("Publishing task update {} for task {}", update, task_id)
        # TODO: think a bit more about whether it is strictly necessary to use the lock here.
        #  mostly this prevents concurrent modifications to the subscription lists,
        with self._subscription_lock:
            logger.bind(
                log_type=MESSAGE_LOG_TYPE, task_id=str(task_id), serialized_message=update.model_dump_json()
            ).trace("Published new message to task listeners")
            if task_id not in self._messages_by_task_id:
                self._messages_by_task_id[task_id] = []
            self._messages_by_task_id[task_id].append(update)

            listeners = self._subscriptions_by_task_id.get(task_id, ())
            for listener in listeners:
                listener.put_nowait(update)

            # also publish to the overall listeners
            task_update = TaskMessageContainer(tasks=(task,), messages=((update, task_id),))
            self._latest_task_by_task_id[task_id] = task

            user_listeners = self._subscriptions_by_user_reference.get(task.user_reference, ())
            for listener in user_listeners:
                listener.put_nowait(task_update)

    @contextmanager
    def _subscribe_to_task(
        self,
        task_id: TaskID,
        filter_fn: Callable[[Message], bool] | None,
    ) -> Generator[Queue[Message], None, None]:
        listener: Queue[Message] = FilteredQueue(filter_fn) if filter_fn else Queue()
        with self._subscription_lock:
            self._subscriptions_by_task_id.setdefault(task_id, []).append(listener)
            # we must query the existing messages for this task inside the lock
            # otherwise there is a race condition where the listener might not see some messages that are being committed
            # or they might arrive out of order (both of which are bad)
            messages = self._messages_by_task_id.get(task_id, [])

        # we make sure that any existing messages are here, thus the subscriber will get all messages
        for message in messages:
            listener.put_nowait(message)

        yield listener

        with self._subscription_lock:
            listeners = self._subscriptions_by_task_id[task_id]
            listeners.remove(listener)
            if not listeners:
                del self._subscriptions_by_task_id[task_id]

    def _notify_about_task_error(
        self,
        user_reference: UserReference,
        task_id: TaskID,
        error: SerializedException,
        transaction: DataModelTransaction,
    ) -> None:
        logger.debug("Publishing task error {!r} for task {}", error, task_id)
        transaction.insert_notification(
            notification=Notification(
                user_reference=user_reference,
                object_id=NotificationID(),
                task_id=task_id,
                importance=NotificationImportance.TIME_SENSITIVE,
                message=str(error) + "\n" + error.as_formatted_traceback(),
            ),
        )

    def _get_services_for_task(self) -> ServiceCollectionForTask:
        return ServiceCollectionForTask(
            settings=self.settings,
            task_service=self,
            data_model_service=self.data_model_service,
            environment_service=self.environment_service,
            secrets_service=self.secrets_service,
            anthropic_credentials_service=self.anthropic_credentials_service,
            git_repo_service=self.git_repo_service,
            project_service=self.project_service,
        )

    def _run_task(self, task: Task, services: ServiceCollectionForTask, settings: SculptorSettings) -> None:
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
                try:
                    maybe_transaction_callback = run_task(
                        task=task,
                        services=services,
                        task_deadline=deadline,
                        settings=settings,
                    )
                    outcome = TaskState.SUCCEEDED
                    logger.debug("Finished running task {}", task.object_id)

                except UserPausedTaskError:
                    with self.data_model_service.open_task_transaction() as transaction:
                        task = transaction.get_task(task.object_id)
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
            # but we do want to be really sure to capture any failures (since this is run in a bare asyncio task)
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
        # finalize task here if it wasn't already finalized
        with self.data_model_service.open_task_transaction() as transaction:
            if outcome == TaskState.DELETED:
                task = transaction.get_task(task.object_id)
                new_task = task.evolve(task.ref().outcome, TaskState.DELETED)
                new_task = new_task.evolve(new_task.ref().is_deleted, True)
                new_task = new_task.evolve(new_task.ref().is_deleting, False)
                transaction.upsert_task(new_task)
                transaction.add_callback(lambda: self._cleanup_task_caches(task.object_id))
                return

            # add any requested data model updates to this transaction
            if maybe_transaction_callback is not None:
                maybe_transaction_callback(transaction)

            # then go make sure we've updated the task outcome
            logged_task = transaction.get_task(task.object_id)
            assert logged_task is not None
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

            # tell the user about any unexpected errors (if they haven't been notified yet)
            if error_to_publish:
                if not is_user_notified:
                    self._notify_about_task_error(
                        user_reference=task.user_reference,
                        task_id=task.object_id,
                        error=error_to_publish,
                        transaction=transaction,
                    )

            # publish the final update message after the transaction has been committed
            assert outcome is not None
            final_update_message = TaskStatusRunnerMessage(outcome=outcome, message_id=AgentMessageID())
            self.create_message(final_update_message, task.object_id, transaction)

    def _cleanup_task_caches(self, task_id: TaskID) -> None:
        with self._subscription_lock:
            self._messages_by_task_id.pop(task_id, None)
            self._latest_task_by_task_id.pop(task_id, None)
