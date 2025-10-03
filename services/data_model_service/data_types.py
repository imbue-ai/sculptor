from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Callable
from typing import Collection

from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.pydantic_serialization import MutableModel
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import UserSettings
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TransactionID
from sculptor.primitives.ids import UserReference


class DataModelTransaction(MutableModel, ABC):
    """
    This is the base class for transactions, ie, for interacting with the database.

    All interaction with the core application state should go through this class.

    Basically this collects all SQL queries into a single place / single set of interface.
    You often want to optimize those queries, so this gives a simple place where you can see all queries at once.

    This is a fairly common pattern known as the "repository pattern" or "data access object (DAO) pattern".
    """

    request_id: RequestID | None
    transaction_id: TransactionID

    @abstractmethod
    def add_callback(self, callback: Callable[[], Any]) -> None:
        """Add a callback to be called after the transaction is committed."""

    @abstractmethod
    def run_post_commit_hooks(self) -> None: ...

    @abstractmethod
    def upsert_project(self, project: Project) -> Project: ...

    @abstractmethod
    def get_projects(self, organization_reference: OrganizationReference | None = None) -> tuple[Project, ...]: ...

    @abstractmethod
    def upsert_user_settings(self, user_settings: UserSettings) -> UserSettings: ...

    @abstractmethod
    def get_user_settings(self, user_reference: UserReference) -> UserSettings | None: ...

    @abstractmethod
    def get_or_create_user_settings(self, user_reference: UserReference) -> UserSettings: ...

    @abstractmethod
    def get_project(self, project_id: ProjectID) -> Project | None: ...

    @abstractmethod
    def insert_notification(self, notification: Notification) -> Notification:
        """
        Notifications enable us to inform users about important events (e.g., task completion, errors, etc.)
        """


class TaskAndDataModelTransaction(DataModelTransaction, ABC):
    """
    This should ONLY be used to expose the SQL data to the task service, and to the tasks themselves.

    Nothing else should use this transaction type!  Instead, go through the task service to interact with tasks.
    This allows the task service to manage notifications, updates, etc.
    """

    @abstractmethod
    def upsert_task(self, task: Task) -> Task: ...

    @abstractmethod
    def get_task(self, task_id: TaskID) -> Task | None: ...

    @abstractmethod
    def get_latest_tasks_for_user(self, user_reference: UserReference, project_id: ProjectID) -> tuple[Task, ...]: ...

    @abstractmethod
    def get_tasks_for_project(
        self,
        project_id: ProjectID,
        is_archived: bool,
        outcomes: Collection[TaskState] | None = None,
        max_results: int | None = None,
    ) -> tuple[Task, ...]: ...

    @abstractmethod
    def insert_message(self, message: SavedAgentMessage) -> SavedAgentMessage: ...


class BaseDataModelTransaction(TaskAndDataModelTransaction, ABC):
    """Generic implementation for transactions that allows adding post-commit callbacks in a very simple way."""

    _post_commit_callbacks: list[Callable[[], None]] = PrivateAttr(default_factory=list)

    def add_callback(self, callback: Callable[[], Any]) -> None:
        self._post_commit_callbacks.append(callback)

    def run_post_commit_hooks(self) -> None:
        for callback in self._post_commit_callbacks:
            callback()
