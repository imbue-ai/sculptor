import datetime
from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Callable
from typing import Collection
from typing import TypedDict

from pydantic import PrivateAttr
from typing_extensions import Unpack

from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import UserSettings
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import DiffStatus
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.foundation.pydantic_serialization import MutableModel
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TransactionID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID


class WorkspaceListingRow(FrozenModel):
    """One denormalized cross-project workspace row from ``get_all_workspaces``.

    Fixed-key structured data, so it is a typed model rather than an ad-hoc dict.
    Field types mirror the web layer's ``RecentWorkspaceResponse`` so the same raw
    SQL values coerce identically; the web layer maps this onto that response.
    """

    object_id: WorkspaceID
    project_id: ProjectID
    description: str
    initialization_strategy: WorkspaceInitializationStrategy
    source_branch: str | None
    environment_id: str | None
    is_deleted: bool
    is_open: bool
    created_at: datetime.datetime
    project_name: str
    # The project's user_git_repo_url (a file:// URL when set), denormalized so
    # the web layer can derive the workspace's working directory without a
    # per-row project lookup.
    project_git_repo_url: str | None
    agent_count: int
    last_activity_at: datetime.datetime


class ProjectFieldUpdate(TypedDict, total=False):
    """Statically-typed allowlist of ``Project`` fields that may be passed to
    :py:meth:`DataModelTransaction.update_project_fields`.

    This is the primary gate on "which fields can be targeted-updated"; the
    runtime ``_UPDATE_FIELDS_PROTECTED_COLUMNS`` check in
    ``sql_implementation.py`` is a defense-in-depth belt.

    ``test_project_field_update_typeddict_matches_project_model`` guards
    against drift between this TypedDict and the ``Project`` model,
    checking both field presence AND type equality.

    Intentionally excluded beyond the universal protected set
    (``object_id`` / ``snapshot_id`` / ``created_at`` / ``is_deleted`` /
    ``is_deleting``):

    * ``organization_reference`` — set at project creation; changing it
      here would effectively re-parent the project to a different
      organization, outside the semantics of a field-level update.
    """

    name: str
    user_git_repo_url: str | None
    is_path_accessible: bool
    default_system_prompt: str | None
    workspace_setup_command: str | None
    naming_pattern: str | None


# Workspace fields excluded from WorkspaceFieldUpdate because they're set
# at workspace creation; changing them via a field-level update would
# re-parent the workspace or violate snapshot-point semantics.  Used by
# the drift-guard test as the inverse of WorkspaceFieldUpdate's keys.
WORKSPACE_CREATION_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "project_id",
        "organization_reference",
        "initialization_strategy",
        "source_branch",
        "source_git_hash",
        "requested_branch_name",
        "harness",
    }
)


class WorkspaceFieldUpdate(TypedDict, total=False):
    """Statically-typed allowlist of ``Workspace`` fields that may be passed to
    :py:meth:`DataModelTransaction.update_workspace_fields`.  Mirrors
    :py:class:`ProjectFieldUpdate`.
    """

    description: str
    target_branch: str | None
    environment_id: str | None
    is_open: bool
    setup_command_triggered: bool
    setup_status: str
    setup_run_id: str | None
    setup_command: str | None
    setup_exit_code: int | None
    setup_started_at: float | None
    setup_finished_at: float | None
    setup_log_path: str | None
    setup_log_truncated: bool
    diff_status: DiffStatus
    diff_updated_at: datetime.datetime | None
    ci_babysitter_paused: bool


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
    def update_project_fields(self, project_id: ProjectID, **fields: Unpack[ProjectFieldUpdate]) -> Project | None:
        """Targeted update on ``project_latest`` that writes ONLY the named columns.

        Unlike :py:meth:`upsert_project` this does NOT assert values for
        unnamed columns, so it's safe against lost-update races on disjoint
        fields across concurrent writers (see SCU-474 for the design
        rationale).

        ``**fields`` is statically validated against :py:class:`ProjectFieldUpdate`
        — type checkers reject unknown field names and wrong value types.

        Returns the full post-update ``Project``, or ``None`` if no row with
        ``object_id == project_id`` exists.
        """

    @abstractmethod
    def get_projects(self, organization_reference: OrganizationReference | None = None) -> tuple[Project, ...]: ...

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

    @abstractmethod
    def get_workspace(self, workspace_id: WorkspaceID) -> Workspace | None: ...

    @abstractmethod
    def get_workspaces(
        self,
        project_id: ProjectID | None = None,
        organization_reference: OrganizationReference | None = None,
    ) -> tuple[Workspace, ...]: ...

    @abstractmethod
    def get_workspace_include_deleted(self, workspace_id: WorkspaceID) -> Workspace | None:
        """Get workspace by ID including soft-deleted ones. Used for deletion state checks."""

    @abstractmethod
    def upsert_workspace(self, workspace: Workspace) -> Workspace: ...

    @abstractmethod
    def update_workspace_fields(
        self, workspace_id: WorkspaceID, **fields: Unpack[WorkspaceFieldUpdate]
    ) -> Workspace | None:
        """Targeted update on ``workspace_latest`` that writes ONLY the named columns.

        Unlike :py:meth:`upsert_workspace` this does NOT assert values for
        unnamed columns, so it's safe against lost-update races on disjoint
        fields across concurrent writers.  Soft-deleted rows are excluded
        from the underlying UPDATE so callers can't write through a
        tombstone.

        Returns the full post-update ``Workspace``, or ``None`` if no
        matching row exists (missing or soft-deleted).
        """

    @abstractmethod
    def get_all_workspaces(self) -> list[WorkspaceListingRow]:
        """Get cross-project workspace listing with denormalized fields, ordered by recent activity."""


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
    def get_tasks_for_user(self, user_reference: UserReference) -> tuple[Task, ...]: ...

    @abstractmethod
    def get_tasks_for_project(
        self,
        project_id: ProjectID,
        outcomes: Collection[TaskState] | None = None,
        max_results: int | None = None,
        input_data_classes: tuple[type, ...] = (),
    ) -> tuple[Task, ...]: ...

    @abstractmethod
    def insert_message(self, message: SavedAgentMessage) -> SavedAgentMessage: ...

    @abstractmethod
    def get_active_tasks(self, input_data_classes: tuple[type, ...] = ()) -> tuple[Task, ...]: ...

    @abstractmethod
    def get_all_tasks(self) -> tuple[Task, ...]: ...

    @abstractmethod
    def get_stuck_deleting_tasks(self) -> tuple[Task, ...]: ...

    @abstractmethod
    def get_messages_for_task(self, task_id: TaskID) -> tuple[SavedAgentMessage, ...]: ...

    @abstractmethod
    def get_messages_for_tasks(self, task_ids: Collection[TaskID]) -> dict[TaskID, tuple[SavedAgentMessage, ...]]: ...


class BaseDataModelTransaction(TaskAndDataModelTransaction, ABC):
    """Generic implementation for transactions that allows adding post-commit callbacks in a very simple way."""

    _post_commit_callbacks: list[Callable[[], None]] = PrivateAttr(default_factory=list)

    def add_callback(self, callback: Callable[[], Any]) -> None:
        self._post_commit_callbacks.append(callback)

    def run_post_commit_hooks(self) -> None:
        for callback in self._post_commit_callbacks:
            callback()
