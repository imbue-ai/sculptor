from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Generator

from pydantic import AnyUrl

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.pydantic_serialization import FrozenModel
from imbue_core.sculptor.state.messages import Message
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import PersistentMessageTypes
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.primitives.ids import UserReference
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.data_types import DataModelTransaction


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
    def create_message(self, message: Message, task_id: TaskID, transaction: DataModelTransaction) -> None: ...

    @abstractmethod
    def get_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task | None: ...

    @abstractmethod
    def get_task_environment(self, task_id: TaskID, transaction: DataModelTransaction) -> Environment | None: ...

    @abstractmethod
    def set_archived(self, task_id: TaskID, is_archived: bool, transaction: DataModelTransaction) -> Task: ...

    @abstractmethod
    def restore_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task: ...

    @abstractmethod
    def delete_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None: ...

    @abstractmethod
    def get_artifact_file_url(self, task_id: TaskID, artifact_name: str) -> AnyUrl: ...

    @abstractmethod
    def set_artifact_file_data(self, task_id: TaskID, artifact_name: str, artifact_data: str | bytes) -> None: ...

    @abstractmethod
    def get_saved_messages_for_task(
        self, task_id: TaskID, transaction: DataModelTransaction
    ) -> tuple[PersistentMessageTypes, ...]: ...

    @abstractmethod
    @contextmanager
    def subscribe_to_complete_tasks_for_user(
        self, user_reference: UserReference, project_id: ProjectID
    ) -> Generator[Queue[TaskMessageContainer], None, None]:
        """
        Returns a queue that receives all task messages some user's tasks.

        Note that for efficiency, only the Message objects used by SimpleAgentView are returned.
        """

    @abstractmethod
    @contextmanager
    def subscribe_to_task(self, task_id: TaskID) -> Generator[Queue[Message], None, None]: ...

    @abstractmethod
    @contextmanager
    def subscribe_to_user_and_sculptor_system_messages(
        self, task_id: TaskID
    ) -> Generator[Queue[Message], None, None]: ...

    @abstractmethod
    def publish_task_update(self, task: Task, update: Message) -> None: ...
