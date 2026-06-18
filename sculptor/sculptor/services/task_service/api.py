from abc import ABC
from abc import abstractmethod
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Generator

from pydantic import AnyUrl

from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import PersistentMessageTypes
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.environments.base import Environment
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.state.messages import Message
from sculptor.state.messages import ModelOption


class TaskMessageContainer(FrozenModel):
    tasks: tuple[Task, ...]
    messages: tuple[tuple[Message, TaskID], ...]


class TaskService(Service, ABC):
    """
    Allows creation, observation, cancellation, and interaction with tasks.

    All interaction with tasks is done by sending and receiving messages.

    LOCAL_ONLY: `Task`s are automatically run by this service when started.

    LOCAL_ONLY: the process running a `Task` does not outlive the server process,
    but the `Task` itself is saved to the database, and thus is persisted indefinitely.
    When the server is restarted, the TaskService will restore the state of all previously running `Task`s
    """

    task_sync_dir: Path

    @abstractmethod
    def create_task(self, task: Task, transaction: DataModelTransaction) -> Task: ...

    @abstractmethod
    def create_message(self, message: MessageTypes, task_id: TaskID, transaction: DataModelTransaction) -> None: ...

    @abstractmethod
    def get_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task | None: ...

    @abstractmethod
    def get_task_environment(self, task_id: TaskID, transaction: DataModelTransaction) -> Environment | None: ...

    @abstractmethod
    def mark_read(self, task_id: TaskID, transaction: DataModelTransaction) -> Task: ...

    @abstractmethod
    def mark_unread(self, task_id: TaskID, transaction: DataModelTransaction) -> Task: ...

    @abstractmethod
    def update_available_models(
        self,
        task_id: TaskID,
        available_models: Sequence[ModelOption],
        current_model: ModelOption | None,
        transaction: DataModelTransaction,
    ) -> Task | None:
        """Persist a harness's model catalog onto the task and publish the update.

        Writes `available_models` / `current_model` onto the task's
        `AgentTaskStateV2` and registers the same task-update publish a message
        write does, so a live switcher refreshes even though no message was
        created. A no-op (returns None) when the catalog already matches or the
        task is missing / not an agent task. The DB title is preserved so a
        concurrent rename is not clobbered."""

    @abstractmethod
    def restore_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task: ...

    @abstractmethod
    def delete_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None: ...

    @abstractmethod
    def get_artifact_file_url(self, task_id: TaskID, artifact_name: str) -> AnyUrl: ...

    @abstractmethod
    def set_artifact_file_data(self, task_id: TaskID, artifact_name: str, artifact_data: str | bytes) -> None: ...

    @abstractmethod
    def ensure_artifact_cache_populated(self, task_id: TaskID, artifact_name: str) -> bool:
        """Return True iff the artifact cache file exists, backfilling from the
        workspace's stable artifacts dir if needed. See SCU-1245."""

    @abstractmethod
    def get_saved_messages_for_task(
        self, task_id: TaskID, transaction: DataModelTransaction
    ) -> tuple[PersistentMessageTypes, ...]: ...

    @abstractmethod
    def get_live_messages_for_task(self, task_id: TaskID) -> tuple[Message, ...]:
        """Snapshot of the task's in-memory messages, INCLUDING ephemeral
        run-scoped ones (e.g. terminal-agent signals) that
        get_saved_messages_for_task never sees."""

    @abstractmethod
    @contextmanager
    def subscribe_to_all_tasks_for_user(
        self, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        """
        Returns a queue that receives all task messages for some user's tasks.

        Note that for efficiency, only the Message objects used by SimpleAgentView are returned.
        """

    @abstractmethod
    @contextmanager
    def subscribe_to_project_task_containers(
        self, project_id: ProjectID, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        """Like subscribe_to_all_tasks_for_user, but narrowed to one project."""

    @abstractmethod
    @contextmanager
    def subscribe_to_workspace_task_containers(
        self, workspace_id: WorkspaceID, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        """Like subscribe_to_all_tasks_for_user, but narrowed to one workspace.

        Tasks whose current_state is None or non-AgentTaskStateV2 have no
        workspace association and are excluded from these subscriptions.
        """

    @abstractmethod
    @contextmanager
    def subscribe_to_single_task_container(
        self, task_id: TaskID, user_reference: UserReference
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        """Like subscribe_to_all_tasks_for_user, but narrowed to one task."""

    @abstractmethod
    @contextmanager
    def subscribe_to_task(self, task_id: TaskID) -> Generator[Queue[Message], None, None]: ...

    @abstractmethod
    @contextmanager
    def subscribe_to_user_and_sculptor_system_messages(
        self, task_id: TaskID
    ) -> Generator[Queue[UserMessageUnion | ResumeAgentResponseRunnerMessage], None, None]: ...
