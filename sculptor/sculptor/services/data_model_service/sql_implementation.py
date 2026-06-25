import functools
import os
import re
import shutil
import sqlite3
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path
from threading import Event
from threading import Lock
from typing import Any
from typing import Callable
from typing import Collection
from typing import Generator
from typing import Generic
from typing import ParamSpec
from typing import TypeVar

import sqlalchemy
import sqlalchemy.exc
from filelock import BaseFileLock
from filelock import Timeout
from filelock import UnixFileLock
from loguru import logger
from pydantic import EmailStr
from pydantic import PrivateAttr
from pydantic.alias_generators import to_snake
from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy import UniqueConstraint
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import select
from sqlalchemy.sql import update
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.schema import Table
from typing_extensions import Unpack

from sculptor.config.settings import SculptorSettings
from sculptor.constants import SCULPTOR_EXIT_CODE_COULD_NOT_ACQUIRE_LOCK
from sculptor.constants import SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR
from sculptor.constants import SCULPTOR_EXIT_CODE_PARENT_DIED
from sculptor.database.automanaged import DatabaseModel
from sculptor.database.automanaged import create_tables
from sculptor.database.core import MigrationsFailedError
from sculptor.database.core import create_new_engine
from sculptor.database.core import initialize_db
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import UserSettings
from sculptor.database.models import Workspace
from sculptor.database.utils import is_read_only_sqlite_url
from sculptor.database.utils import maybe_get_db_path
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.log_utils import log_and_exit_program
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import ObjectID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import TransactionID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import UserSettingsID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.data_model_service.api import TQ
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.data_types import BaseDataModelTransaction
from sculptor.services.data_model_service.data_types import ProjectFieldUpdate
from sculptor.services.data_model_service.data_types import WorkspaceFieldUpdate
from sculptor.services.data_model_service.data_types import WorkspaceListingRow
from sculptor.utils.process_utils import get_original_parent_pid
from sculptor.utils.type_utils import extract_leaf_types

USER_SETTINGS_TABLE, USER_SETTINGS_LATEST_TABLE = create_tables(
    to_snake(UserSettings.__name__),
    UserSettings,
    constraints=(UniqueConstraint("user_reference", name="unique_user_reference"),),
)

PROJECT_TABLE, PROJECT_LATEST_TABLE = create_tables(
    to_snake(Project.__name__),
    Project,
    # NOTE: Project's is_deleted is intentionally NOT latched.  Project
    # initialization (ProjectServiceImpl._initialize_project) re-uses
    # existing project rows and clears is_deleted to resurrect a previously
    # soft-deleted project when the user re-initializes the same repo.
    # Latching here would break that flow.
)

WORKSPACE_TABLE, WORKSPACE_LATEST_TABLE = create_tables(
    to_snake(Workspace.__name__),
    Workspace,
    constraints=(
        ForeignKeyConstraint(
            ["project_id"], [f"{PROJECT_LATEST_TABLE.name}.object_id"], name="foreign_key_workspace_project_id"
        ),
    ),
    # Soft-delete must latch: e.g. refresh_workspace_diff reads the workspace,
    # does slow disk I/O, then upserts diff_status=READY — if a concurrent
    # delete commits is_deleted=True in between, the full-object re-upsert
    # would otherwise revive it (SCU-168).  Mirrors Task.
    #
    # Partial fix: the trigger's MAX(latest.is_deleted, excluded.is_deleted)
    # reads `latest.is_deleted` through the writer's snapshot, which under
    # SQLite WAL + BEGIN DEFERRED may still be the pre-delete value.  Closes
    # the observed race in most cases but a stricter TOCTOU-safe fix
    # (re-read after write, or row-level locking) is tracked in SCU-168.
    monotonic_columns=frozenset({"is_deleted"}),
)

TASK_TABLE, TASK_LATEST_TABLE = create_tables(
    to_snake(Task.__name__),
    Task,
    constraints=(
        ForeignKeyConstraint(
            ["project_id"], [f"{PROJECT_LATEST_TABLE.name}.object_id"], name="foreign_key_project_id"
        ),
    ),
    monotonic_columns=frozenset({"is_deleting", "is_deleted"}),
)

SAVED_AGENT_MESSAGE_TABLE, _ = create_tables(
    to_snake(SavedAgentMessage.__name__),
    SavedAgentMessage,
    constraints=(
        ForeignKeyConstraint(["task_id"], [f"{TASK_LATEST_TABLE.name}.object_id"], name="foreign_key_task_id"),
    ),
    # We don't need a latest table for saved agent messages -- it's really just a log
    is_dual_table=False,
)
Index(
    "ix_saved_agent_message_task_id_created_at",
    SAVED_AGENT_MESSAGE_TABLE.c.task_id,
    SAVED_AGENT_MESSAGE_TABLE.c.created_at,
)

NOTIFICATION_TABLE, _ = create_tables(
    to_snake(Notification.__name__),
    Notification,
    constraints=(
        ForeignKeyConstraint(["task_id"], [f"{TASK_LATEST_TABLE.name}.object_id"], name="foreign_key_task_id"),
    ),
    # We don't need a latest table for notifications -- they are not edited
    is_dual_table=False,
)


T2 = TypeVar("T2", bound=DatabaseModel)
T4 = TypeVar("T4", bound=Project | UserSettings | Notification | Task | Workspace)

_WAIT_FOR_LOCK_TIMEOUT_SEC = 10.0


P = ParamSpec("P")
R = TypeVar("R")


def overwrite_missing_table_error_for_sentry(
    func: Callable[P, R],
) -> Callable[P, R]:
    """Replace sqlite3.OperationalError with MissingSQLTableError when it's for a missing table."""

    _missing_table_regex = re.compile(r"no such table: (\w+)")

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except sqlite3.OperationalError as e:
            match = _missing_table_regex.search(str(e))
            if match:
                raise MissingSQLTableError(match.group(1)) from e
            raise

    return wrapper


class SQLTransaction(BaseDataModelTransaction):
    connection: Connection
    # tracks the current stack. Useful for debugging if we get a "database is locked" error.
    call_stack: str
    _updated_models: list[tuple[str, DatabaseModel]] = PrivateAttr(default_factory=list)
    _start_time: float = PrivateAttr(default_factory=lambda: time.monotonic())

    def get_updated_models(self) -> list[tuple[str, DatabaseModel]]:
        return self._updated_models

    def upsert_project(self, project: Project) -> Project:
        return self._upsert_model(project, PROJECT_TABLE, self.get_project)

    def update_project_fields(self, project_id: ProjectID, **fields: Unpack[ProjectFieldUpdate]) -> Project | None:
        # ``fields`` is a TypedDict at the type level but a plain ``dict`` at
        # runtime; ``_update_model_fields`` wants ``dict[str, Any]``.
        return self._update_model_fields(
            model_cls=Project,
            snapshot_table=PROJECT_TABLE,
            latest_table=PROJECT_LATEST_TABLE,
            object_id=project_id,
            fields={**fields},
        )

    def get_projects(self, organization_reference: OrganizationReference | None = None) -> tuple[Project, ...]:
        statement = select(PROJECT_LATEST_TABLE).where(PROJECT_LATEST_TABLE.c.is_deleted == False)  # noqa: E712
        if organization_reference is not None:
            statement = statement.where(PROJECT_LATEST_TABLE.c.organization_reference == str(organization_reference))
        result = self.connection.execute(statement)
        return tuple(_row_to_pydantic_model(row, Project) for row in result.all())

    def get_project(self, project_id: ProjectID) -> Project | None:
        statement = select(PROJECT_LATEST_TABLE).where(PROJECT_LATEST_TABLE.c.object_id == str(project_id))
        result = self.connection.execute(statement)
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_pydantic_model(row, Project)

    @overwrite_missing_table_error_for_sentry
    def get_user_settings(self, user_reference: UserReference) -> UserSettings | None:
        statement = select(USER_SETTINGS_LATEST_TABLE).where(
            USER_SETTINGS_LATEST_TABLE.c.user_reference == str(user_reference)
        )
        result = self.connection.execute(statement)
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_pydantic_model(row, UserSettings)

    @overwrite_missing_table_error_for_sentry
    def get_or_create_user_settings(self, user_reference: UserReference) -> UserSettings:
        user_settings = self.get_user_settings(user_reference)
        if user_settings is not None:
            return user_settings
        logger.debug("Creating user settings for {}", user_reference)
        user_settings = UserSettings(object_id=UserSettingsID(), user_reference=user_reference)
        statement = USER_SETTINGS_TABLE.insert().values(**_pydantic_model_to_row_values(user_settings))
        try:
            self.connection.execute(statement)
        except (sqlalchemy.exc.IntegrityError, sqlite3.IntegrityError):
            # If the user settings already exist (e.g. because it was created in another thread), it's fine.
            logger.debug("User settings already created for {}; falling back to what is in the DB", user_reference)

        user_settings = self.get_user_settings(user_reference)
        assert user_settings is not None
        return user_settings

    def insert_notification(self, notification: Notification) -> Notification:
        self._insert_model(notification, NOTIFICATION_TABLE)
        return notification

    @overwrite_missing_table_error_for_sentry
    def get_workspace(self, workspace_id: WorkspaceID) -> Workspace | None:
        statement = (
            select(WORKSPACE_LATEST_TABLE)
            .where(WORKSPACE_LATEST_TABLE.c.object_id == str(workspace_id))
            .where(WORKSPACE_LATEST_TABLE.c.is_deleted.is_(False))
        )
        result = self.connection.execute(statement)
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_pydantic_model(row, Workspace)

    @overwrite_missing_table_error_for_sentry
    def get_workspace_include_deleted(self, workspace_id: WorkspaceID) -> Workspace | None:
        """Get workspace by ID including soft-deleted ones. Used for deletion state checks."""
        statement = select(WORKSPACE_LATEST_TABLE).where(WORKSPACE_LATEST_TABLE.c.object_id == str(workspace_id))
        result = self.connection.execute(statement)
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_pydantic_model(row, Workspace)

    @overwrite_missing_table_error_for_sentry
    def get_workspaces(
        self,
        project_id: ProjectID | None = None,
        organization_reference: OrganizationReference | None = None,
    ) -> tuple[Workspace, ...]:
        statement = select(WORKSPACE_LATEST_TABLE).where(WORKSPACE_LATEST_TABLE.c.is_deleted.is_(False))
        if project_id is not None:
            statement = statement.where(WORKSPACE_LATEST_TABLE.c.project_id == str(project_id))
        if organization_reference is not None:
            statement = statement.where(WORKSPACE_LATEST_TABLE.c.organization_reference == str(organization_reference))
        result = self.connection.execute(statement)
        return tuple(_row_to_pydantic_model(row, Workspace) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def upsert_workspace(self, workspace: Workspace) -> Workspace:
        return self._upsert_model(workspace, WORKSPACE_TABLE, self.get_workspace)

    @overwrite_missing_table_error_for_sentry
    def update_workspace_fields(
        self, workspace_id: WorkspaceID, **fields: Unpack[WorkspaceFieldUpdate]
    ) -> Workspace | None:
        # is_deleted is latched on Workspace; refuse writes through tombstones.
        return self._update_model_fields(
            model_cls=Workspace,
            snapshot_table=WORKSPACE_TABLE,
            latest_table=WORKSPACE_LATEST_TABLE,
            object_id=workspace_id,
            fields={**fields},
            latest_where_extra=WORKSPACE_LATEST_TABLE.c.is_deleted.is_(False),
        )

    @overwrite_missing_table_error_for_sentry
    def get_all_workspaces(self) -> list[WorkspaceListingRow]:
        """Get cross-project workspace listing with denormalized fields, ordered by recent activity."""
        rows = self.connection.execute(
            text("""
                SELECT
                    w.object_id,
                    w.project_id,
                    w.description,
                    w.initialization_strategy,
                    w.source_branch,
                    w.is_deleted,
                    w.is_open,
                    w.created_at,
                    p.name AS project_name,
                    COUNT(CASE
                        WHEN t.is_deleted = 0
                         AND json_extract(t.current_state, '$.workspace_id') = w.object_id
                         AND json_extract(t.current_state, '$.object_type') = 'AgentTaskStateV2'
                        THEN 1
                    END) AS agent_count,
                    COALESCE(
                        MAX(CASE
                            WHEN json_extract(t.current_state, '$.workspace_id') = w.object_id
                             AND t.is_deleted = 0
                            THEN t.created_at
                        END),
                        w.created_at
                    ) AS last_activity_at
                FROM workspace_latest w
                JOIN project_latest p ON w.project_id = p.object_id
                LEFT JOIN task_latest t ON json_extract(t.current_state, '$.workspace_id') = w.object_id
                WHERE w.is_deleted = 0
                  AND p.is_deleted = 0
                GROUP BY w.object_id
                ORDER BY last_activity_at DESC
            """)
        ).all()

        return [WorkspaceListingRow(**{str(k): v for k, v in row._mapping.items()}) for row in rows]

    @overwrite_missing_table_error_for_sentry
    def upsert_task(self, task: Task) -> Task:
        return self._upsert_model(task, TASK_TABLE, self.get_task)

    @overwrite_missing_table_error_for_sentry
    def get_task(self, task_id: TaskID) -> Task | None:
        statement = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.object_id == str(task_id))
            .where(TASK_LATEST_TABLE.c.is_deleted.is_(False))
        )
        result = self.connection.execute(statement)
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_pydantic_model(row, Task)

    @overwrite_missing_table_error_for_sentry
    def get_tasks_for_project(
        self,
        project_id: ProjectID,
        outcomes: Collection[TaskState] | None = None,
        max_results: int | None = None,
        input_data_classes: tuple[type, ...] = (),
    ) -> tuple[Task, ...]:
        query = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.project_id == str(project_id))
            .where(TASK_LATEST_TABLE.c.is_deleted.is_(False))
            .where(TASK_LATEST_TABLE.c.is_deleting.is_(False))
            .order_by(TASK_LATEST_TABLE.c.created_at)
        )
        if outcomes is not None:
            query = query.where(TASK_LATEST_TABLE.c.outcome.in_(outcomes))
        if max_results is not None:
            query = query.limit(max_results)
        if len(input_data_classes) > 0:
            input_data_class_names = tuple(cls.__name__ for cls in input_data_classes)
            query = query.where(TASK_LATEST_TABLE.c.input_data["object_type"].as_string().in_(input_data_class_names))
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def get_all_tasks(self) -> tuple[Task, ...]:
        query = select(TASK_LATEST_TABLE).order_by(TASK_LATEST_TABLE.c.created_at)
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def get_stuck_deleting_tasks(self) -> tuple[Task, ...]:
        query = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.is_deleting.is_(True))
            .where(TASK_LATEST_TABLE.c.is_deleted.is_(False))
            .order_by(TASK_LATEST_TABLE.c.created_at)
        )
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def get_active_tasks(self, input_data_classes: tuple[type, ...] = ()) -> tuple[Task, ...]:
        query = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.is_deleted.is_(False))
            .where(TASK_LATEST_TABLE.c.is_deleting.is_(False))
        )
        if len(input_data_classes) > 0:
            input_data_class_names = tuple(cls.__name__ for cls in input_data_classes)
            query = query.where(TASK_LATEST_TABLE.c.input_data["object_type"].as_string().in_(input_data_class_names))
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    def insert_message(self, message: SavedAgentMessage) -> SavedAgentMessage:
        self._insert_model(message, SAVED_AGENT_MESSAGE_TABLE)
        return message

    def get_messages_for_task(self, task_id: TaskID) -> tuple[SavedAgentMessage, ...]:
        query = (
            select(SAVED_AGENT_MESSAGE_TABLE)
            .where(SAVED_AGENT_MESSAGE_TABLE.c.task_id == str(task_id))
            # FIXME: ordering by created_at alone is non-deterministic when two messages share a
            #  timestamp; this log needs a monotonic/auto-incrementing ordering key.
            .order_by(SAVED_AGENT_MESSAGE_TABLE.c.created_at)
        )
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, SavedAgentMessage) for row in result.all())

    def get_messages_for_tasks(self, task_ids: Collection[TaskID]) -> dict[TaskID, tuple[SavedAgentMessage, ...]]:
        if not task_ids:
            return {}
        query = (
            select(SAVED_AGENT_MESSAGE_TABLE)
            .where(SAVED_AGENT_MESSAGE_TABLE.c.task_id.in_([str(tid) for tid in task_ids]))
            .order_by(SAVED_AGENT_MESSAGE_TABLE.c.task_id, SAVED_AGENT_MESSAGE_TABLE.c.created_at)
        )
        result = self.connection.execute(query)
        messages_by_task: dict[TaskID, list[SavedAgentMessage]] = {}
        for row in result.all():
            msg = _row_to_pydantic_model(row, SavedAgentMessage)
            messages_by_task.setdefault(msg.task_id, []).append(msg)
        return {tid: tuple(msgs) for tid, msgs in messages_by_task.items()}

    @overwrite_missing_table_error_for_sentry
    def get_tasks_for_user(self, user_reference: UserReference) -> tuple[Task, ...]:
        """Get all non-deleted tasks for a user in a project."""
        query = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.user_reference == str(user_reference))
            .where(TASK_LATEST_TABLE.c.is_deleted.is_(False))
            .where(TASK_LATEST_TABLE.c.is_deleting.is_(False))
            .order_by(TASK_LATEST_TABLE.c.created_at.desc())
        )
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    def _insert_model(self, obj: DatabaseModel, table: Table) -> DatabaseModel:
        """
        Insert a model into the database and add to database operations tracking.
        """
        logger.debug("Inserting {}", obj.__class__.__name__)
        statement = table.insert().values(**_pydantic_model_to_row_values(obj))
        result = self.connection.execute(statement)
        assert result.rowcount == 1, "Expected exactly one row to be inserted"

        self._updated_models.append(("INSERT", obj))

        return obj

    def _update_model_fields(
        self,
        model_cls: type[T4],
        snapshot_table: Table,
        latest_table: Table,
        object_id: ObjectID,
        fields: dict[str, Any],
        latest_where_extra: ColumnElement[bool] | None = None,
    ) -> T4 | None:
        """Targeted update: write ONLY the named columns to the ``_latest``
        table, then write a snapshot row from the resulting post-update
        values.

        ``latest_where_extra`` is AND-ed onto the ``object_id`` filter for
        the LATEST UPDATE — used to refuse writes through soft-delete
        tombstones (e.g. ``Workspace.is_deleted``).

        Returns the full post-update model, or ``None`` if no row matched.
        """
        if not fields:
            raise ValueError(f"update_{model_cls.__name__.lower()}_fields requires at least one field")

        model_field_names = set(model_cls.model_fields.keys())
        for name in fields:
            if name in _UPDATE_FIELDS_PROTECTED_COLUMNS:
                raise ValueError(
                    f"Field {name!r} is managed by the database or has a separate API (e.g. delete_*); refuse to write it via update_*_fields"
                )
            if name not in model_field_names:
                raise ValueError(f"Unknown {model_cls.__name__} field: {name!r}")

        serialized_fields = {name: _pydantic_value_to_row_value(value) for name, value in fields.items()}

        logger.debug("Updating {} fields: {}", model_cls.__name__, sorted(fields.keys()))

        update_stmt = (
            update(latest_table)
            .where(latest_table.c.object_id == str(object_id))
            .values(**serialized_fields)
            .returning(*latest_table.c)
        )
        if latest_where_extra is not None:
            update_stmt = update_stmt.where(latest_where_extra)
        result = self.connection.execute(update_stmt)
        row = result.fetchone()
        if row is None:
            # No row matched — row doesn't exist (or was already deleted if
            # our WHERE had filtered that; currently we don't, but
            # targeted updaters on a specific table could add such a filter
            # at the model-specific wrapper above).
            return None

        updated_model = _row_to_pydantic_model(row, model_cls)

        # Write a snapshot row for audit history.  The existing
        # ``<table>_before_insert`` trigger will fire on this INSERT and
        # redundantly UPDATE the ``_latest`` row with identical values;
        # that's a cosmetic cost, not a correctness issue.  See notes.md.
        snapshot_stmt = snapshot_table.insert().values(**_pydantic_model_to_row_values(updated_model))
        self.connection.execute(snapshot_stmt)

        self._updated_models.append(("UPDATE", updated_model))
        return updated_model

    def _upsert_model(
        self,
        obj: T4,
        table: Table,
        getter: Callable[..., T4 | None],
    ) -> T4:
        logger.debug("Upserting {}", obj.__class__.__name__)
        existing_object = getter(obj.object_id)
        operation = None

        if existing_object is not None:
            if existing_object.is_content_equal(obj):
                # No operation, so we don't need to make a db call or add this to our updated models.
                return existing_object
            else:
                operation = "UPDATE"
        else:
            operation = "INSERT"

        statement = table.insert().values(**_pydantic_model_to_row_values(obj))
        result = self.connection.execute(statement)
        assert result.rowcount == 1, "Expected exactly one row to be inserted"

        self._updated_models.append((operation, obj))

        return obj


_serializable_fields_cache: dict[type, frozenset[str]] = {}


def _get_serializable_fields(model_cls: type) -> frozenset[str]:
    """Return field names where the type contains a SerializableModel leaf, cached per model class."""
    cached = _serializable_fields_cache.get(model_cls)
    if cached is not None:
        return cached
    result: set[str] = set()
    for field_name, field in model_cls.model_fields.items():
        leaf_types = extract_leaf_types(field.annotation)
        if any(isinstance(lt, type) and issubclass(lt, SerializableModel) for lt in leaf_types):
            result.add(field_name)
    frozen = frozenset(result)
    _serializable_fields_cache[model_cls] = frozen
    return frozen


def _row_to_pydantic_model(row: sqlalchemy.Row, model_cls: type[T2]) -> T2:
    serializable_fields = _get_serializable_fields(model_cls)
    values = {}
    for field_name in model_cls.model_fields:
        row_value = getattr(row, field_name)
        if row_value is not None and field_name in serializable_fields:
            values[field_name] = row_value
            continue
        if row_value is not None and isinstance(row_value, datetime) and row_value.tzinfo is None:
            # For naive datetime objects, assume UTC.
            # (We store stuff as UTC but e.g. sqlite does not support timezones so the values come back as naive.)
            row_value = row_value.replace(tzinfo=timezone.utc)
        values[field_name] = row_value
    return model_cls.model_validate(values)


def _pydantic_model_to_row_values(model: T2) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field_name, _field in model.__class__.model_fields.items():
        values[field_name] = _pydantic_value_to_row_value(getattr(model, field_name))
    return values


def _pydantic_value_to_row_value(value: Any) -> Any:
    """Serialize a single Python value for storage, matching the per-field
    logic in :py:func:`_pydantic_model_to_row_values`.

    Kept as a separate helper so targeted-column updaters
    (``update_*_fields``) can serialize individual values without
    constructing a full model instance.
    """
    if isinstance(value, SerializableModel):
        return value.model_dump(mode="json")
    if isinstance(value, ObjectID):
        return str(value)
    # pyrefly: ignore [invalid-argument]
    if isinstance(value, EmailStr):
        return str(value)
    return value


# Columns that ``update_*_fields`` refuses to write.  ``object_id`` and
# ``snapshot_id`` are identity columns; ``created_at`` is populated by the
# ``AFTER INSERT`` trigger on the snapshot row.  ``is_deleted`` (and
# ``is_deleting`` on Task) has a latched, separate-path API for deletion —
# allowing a targeted update to set it would bypass the monotonic
# semantics and be a footgun.
#
# This runtime check is a belt alongside the suspenders of the
# per-model ``<Model>FieldUpdate`` ``TypedDict``s below, which are the
# primary (statically-enforced) gate.
_UPDATE_FIELDS_PROTECTED_COLUMNS: frozenset[str] = frozenset(
    {"object_id", "snapshot_id", "created_at", "is_deleted", "is_deleting"}
)


# ``ProjectFieldUpdate`` is the statically-typed allowlist of fields that
# may be passed to :py:meth:`update_project_fields`.  Defined alongside the
# abstract in ``data_types`` so callers import it next to the method.  See
# there for the exclusion rationale.


# Keep a reference to the lock to prevent garbage collection.
_GLOBAL_SCULPTOR_INSTANCE_LOCK_TO_PREVENT_CONCURRENT_DB_ACCESS: BaseFileLock | None = None


class SQLDataModelService(TaskDataModelService, Generic[TQ]):
    _engine: Engine = PrivateAttr()
    _observers_by_user_reference: dict[UserReference, list[TQ]] = PrivateAttr(default_factory=dict)
    # Observers are registered/unregistered from websocket handler threads while
    # open_transaction reads them from request threads, so all access to
    # _observers_by_user_reference must hold this lock.
    _observers_lock: Lock = PrivateAttr(default_factory=Lock)
    _is_started: bool = PrivateAttr(default=False)
    # Use this flag to skip initialization if the service is running in read-only mode.
    _is_read_only: bool = PrivateAttr(default=False)
    # we track the currently active transactions for debugging -- we want to know what takes a long time when the DB is locked
    _active_transaction_by_id: dict[TransactionID, SQLTransaction] = PrivateAttr(default_factory=dict)
    # ensure that our parent process doesn't disappear. If it does, we must exit
    _parent_watch_shutdown_event: Event = PrivateAttr(default_factory=Event)

    @classmethod
    def build_from_settings(
        cls, settings: SculptorSettings, concurrency_group: ConcurrencyGroup
    ) -> "SQLDataModelService":
        # Create directory for SQLite file-based databases if needed
        db_path = maybe_get_db_path(settings.DATABASE_URL)
        if db_path is not None:
            db_dir = db_path.parent
            if not db_dir.exists():
                logger.info("Creating database directory: {}", db_dir)
                db_dir.mkdir(parents=True, exist_ok=True)
        engine = create_new_engine(settings.DATABASE_URL)
        data_model_service = cls(concurrency_group=concurrency_group)
        data_model_service._engine = engine
        return data_model_service

    def _initialize(self) -> None:
        assert not self._is_read_only, "SQLDataModelService should not be initialized in the read-only mode."
        db_path = maybe_get_db_path(str(self._engine.url))

        if db_path is not None:
            parent_pid = get_original_parent_pid()
            global _GLOBAL_SCULPTOR_INSTANCE_LOCK_TO_PREVENT_CONCURRENT_DB_ACCESS
            # Prevent accidental concurrent migrations.
            # The start() method is supposed to run exactly once when Sculptor starts.
            # If it runs more than once, something is wrong.
            # By using the UnixFileLock, we ensure release of the lock even if the process crashes.
            # (There's no need to explicitly release.)
            # If we ever start supporting windows, we can easily add a WindowsFileLock here.
            # (Using plain FileLock seems to not get released on process crash.)
            try:
                if _GLOBAL_SCULPTOR_INSTANCE_LOCK_TO_PREVENT_CONCURRENT_DB_ACCESS is None:
                    _GLOBAL_SCULPTOR_INSTANCE_LOCK_TO_PREVENT_CONCURRENT_DB_ACCESS = UnixFileLock(
                        db_path.with_suffix(".lock")
                    )
                _GLOBAL_SCULPTOR_INSTANCE_LOCK_TO_PREVENT_CONCURRENT_DB_ACCESS.acquire(
                    timeout=_WAIT_FOR_LOCK_TIMEOUT_SEC
                )
            except Timeout as error:
                message = (
                    "Database is already in use. Maybe another Sculptor instance is running with the same database?"
                )
                logger.opt(exception=error).info(
                    "Irrecoverable exception encountered. Terminating the program immediately."
                )
                log_and_exit_program(SCULPTOR_EXIT_CODE_COULD_NOT_ACQUIRE_LOCK, message)
            # as soon as we've started holding this lock, we need to make sure that we are going to exit if our parent dies
            # this is important because our parent is, in the general case, the electron process
            # if the user hard exits that process, they might not expect that the python server is still running
            # (typically, this shouldn't happen, though - we expect the parent to cleanly shut down the server)
            self.concurrency_group.start_new_thread(target=self._watch_parent_process, daemon=True, args=(parent_pid,))

        has_backup = False
        if db_path is not None and db_path.exists():
            # We're running with an SQLite database.
            # That typically means we're either testing or we're running a local sculptor instance.
            # We want to avoid letting users of local instances bork their installations because of buggy DB migrations.

            # 1. Make sure the .wal and .shm files are empty before we start.
            with self._engine.connect() as connection:
                connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))

            # 2. Copy the database file to a temporary location.
            logger.info("database startup: copying db file to backup location.")
            shutil.copy(db_path, _get_backup_db_path(db_path))
            has_backup = True

        try:
            initialize_db(self._engine)
        except MigrationsFailedError as error:
            # 2. If migrations fail, restore the original database file from the temporary location.
            if has_backup:
                logger.info("database migration failed: Restoring original db file from backup location.")
                assert db_path is not None
                shutil.copy(_get_backup_db_path(db_path), db_path)
                # 3. Remove any remaining .wal and .shm files from the failed migration if they exist.
                db_path.with_suffix(".wal").unlink(missing_ok=True)
                db_path.with_suffix(".shm").unlink(missing_ok=True)
            if error.is_likely_a_result_of_sculptor_downgrade:
                log_and_exit_program(
                    SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR,
                    "Sculptor database is not compatible (have you downgraded Sculptor?). Terminating.",
                )

            logger.error("database startup: failed to run migrations for the newest version. Please contact support.")
            raise

    def _watch_parent_process(self, parent_pid: int) -> None:
        while not self._parent_watch_shutdown_event.wait(timeout=_WAIT_FOR_LOCK_TIMEOUT_SEC / 2.2):
            if os.getppid() != parent_pid:
                logger.info("Parent process has exited, so we are exiting too.")
                # note that we VERY SPECIFICALLY DO NOT CALL log_and_exit_program
                # that is because we MUST exit immediately -- otherwise the user might not be able to start sculptor again
                # because the database file is locked
                os._exit(SCULPTOR_EXIT_CODE_PARENT_DIED)

    def start(self) -> None:
        assert not self._is_started, "SQLDataModelService can only be started once."
        if self._is_read_only:
            if not is_read_only_sqlite_url(str(self._engine.url)):
                raise ReadOnlyConnectionStringExpectedError(
                    "SQLDataModelService is configured to be read-only, but the database URL is not a read-only SQLite URL."
                )
        else:
            self._initialize()
        self._is_started = True

    def stop(self) -> None:
        self._parent_watch_shutdown_event.set()

    @contextmanager
    def open_task_transaction(self, *, immediate: bool = False) -> Generator[SQLTransaction, None, None]:
        with self.open_transaction(RequestID(), is_user_request=False, immediate=immediate) as transaction:
            yield transaction

    @contextmanager
    def _begin_immediate_connection(self) -> Generator[Connection, None, None]:
        """Yield a connection that runs in a ``BEGIN IMMEDIATE`` transaction.

        The default ``engine.begin()`` path goes through pysqlite's
        auto-BEGIN, which can only emit ``BEGIN DEFERRED`` and leaves
        read-then-write paths exposed to stale-snapshot races (SCU-168).
        Here we set ``isolation_level="AUTOCOMMIT"`` so SQLAlchemy doesn't
        wrap the connection in its own transaction, then emit ``BEGIN
        IMMEDIATE`` ourselves and explicitly COMMIT/ROLLBACK.

        BEGIN IMMEDIATE acquires the writer slot at transaction start, so
        any concurrent writer that committed before us is visible in our
        snapshot, and another writer can't sneak in between our read and
        our write.

        See SQLAlchemy's pysqlite notes:
        https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl
        """
        with self._engine.connect() as connection:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.exec_driver_sql("ROLLBACK")
                raise
            else:
                connection.exec_driver_sql("COMMIT")

    @contextmanager
    def open_transaction(
        self,
        request_id: RequestID,
        is_user_request: bool = True,
        *,
        immediate: bool = False,
    ) -> Generator[SQLTransaction, None, None]:
        """Open a SQL transaction.

        Args:
            immediate: If True, emit ``BEGIN IMMEDIATE`` so the writer slot
                is acquired at transaction start.  Use for read-then-write
                paths where a stale snapshot could cause data loss
                (SCU-168).  Defaults to False (``BEGIN DEFERRED`` via
                pysqlite's auto-BEGIN), which preserves read concurrency.
        """
        if not self._is_started:
            raise AttemptedOperationBeforeStartError(
                "SQLDataModelService must be started before opening transactions."
            )
        transaction_id = TransactionID()
        call_stack = "".join(traceback.format_stack())
        start_time = time.monotonic()
        connection_cm = self._begin_immediate_connection() if immediate else self._engine.begin()
        # Single OperationalError handler covering both connection acquisition
        # (where BEGIN IMMEDIATE may raise "database is locked" before any
        # SQLTransaction exists, SCU-536) and the yielded body (where lazy
        # BEGIN DEFERRED or any other statement may raise the same).
        try:
            with connection_cm as connection:
                transaction = SQLTransaction(
                    request_id=request_id,
                    connection=connection,
                    transaction_id=transaction_id,
                    call_stack=call_stack,
                )
                # Track wait-for-BEGIN time too, not just body time.
                transaction._start_time = start_time
                with logger.contextualize(transaction_id=transaction.transaction_id):
                    self._active_transaction_by_id[transaction_id] = transaction
                    try:
                        yield transaction
                    finally:
                        del self._active_transaction_by_id[transaction_id]
        except OperationalError as e:
            if "database is locked" in str(e):
                transaction_summary = self._format_lock_debug_summary(
                    transaction_id=transaction_id,
                    call_stack=call_stack,
                    start_time=start_time,
                )
                log_exception(
                    e,
                    "Database is locked, inspect extra data to see why",
                    sentry_extra=dict(transaction_summary=transaction_summary),
                )
            raise

        transaction.run_post_commit_hooks()

        # Filter database operations to only include observable models (Project, User, Notification, Workspace)
        # The observer system only cares about these specific model types, not all database operations
        observable_models = []
        for operation, model in transaction.get_updated_models():
            if isinstance(model, (Project, UserSettings, Notification, Workspace)):
                observable_models.append(model)

        completed_transaction = CompletedTransaction(request_id=request_id, updated_models=tuple(observable_models))

        # ignore read-only requests from tasks
        if not is_user_request and len(completed_transaction.updated_models) == 0:
            return
        # Snapshot under the lock, then notify outside it: websocket threads
        # mutate the dict concurrently (iterating it directly raised
        # "dictionary changed size during iteration"), and keeping put() calls
        # outside the lock means a slow observer cannot block registration.
        with self._observers_lock:
            observers = [
                observer for observer_list in self._observers_by_user_reference.values() for observer in observer_list
            ]
        for observer in observers:
            observer.put(completed_transaction)

    def _format_lock_debug_summary(
        self,
        *,
        transaction_id: TransactionID,
        call_stack: str,
        start_time: float,
    ) -> str:
        """Build the lock-debug summary used when "database is locked" surfaces.

        Accepts raw fields rather than an ``SQLTransaction`` so it works for
        BEGIN-IMMEDIATE failures where the connection never opened and no
        ``SQLTransaction`` exists (SCU-536).
        """
        now = time.monotonic()
        transaction_summary_entries = [
            f"Took {now - start_time:.2f}s to run this transaction, which failed:\n{call_stack}\n"
        ]
        other_transactions = sorted(
            [
                (now - x._start_time, x.call_stack)
                for x in self._active_transaction_by_id.values()
                if x.transaction_id != transaction_id
            ],
            reverse=True,
        )
        transaction_summary_entries.append(f"{len(other_transactions)} other active transactions:\n")
        for age, stack in other_transactions:
            transaction_summary_entries.append(f"ACTIVE FOR {age:.2f}s:\n{stack}\n")
        transaction_summary = "\n".join(transaction_summary_entries)
        return transaction_summary

    @contextmanager
    # pyrefly: ignore [bad-override]
    def observe_user_changes(
        self, user_reference: UserReference, organization_reference: OrganizationReference, queue: TQ
    ) -> Generator[TQ, None, None]:
        with self._observers_lock:
            self._observers_by_user_reference[user_reference] = self._observers_by_user_reference.get(
                user_reference, []
            ) + [queue]

        # put the current project, workspace, and user in the queue
        with self.open_transaction(RequestID()) as transaction:
            user_settings = transaction.get_user_settings(user_reference)
            assert user_settings is not None
            projects = transaction.get_projects(organization_reference)
            workspaces = transaction.get_workspaces(organization_reference=organization_reference)

        existing_models: list[Project | UserSettings | Notification | Workspace] = [user_settings]
        for project in projects:
            existing_models.append(project)
        for workspace in workspaces:
            existing_models.append(workspace)
        queue.put(CompletedTransaction(request_id=None, updated_models=tuple(existing_models)))

        try:
            yield queue
        finally:
            with self._observers_lock:
                self._observers_by_user_reference[user_reference].remove(queue)
                if not self._observers_by_user_reference[user_reference]:
                    del self._observers_by_user_reference[user_reference]


class MissingSQLTableError(sqlite3.OperationalError):
    """Raised when an SQLite operation fails because a table is missing."""

    def __init__(self, table: str):
        # just put the table name in args
        super().__init__(table)
        self.table = table


class AttemptedOperationBeforeStartError(Exception):
    pass


class ReadOnlyConnectionStringExpectedError(Exception):
    pass


def _get_backup_db_path(db_path: Path) -> Path:
    return db_path.with_suffix(".backup")


def register_all_tables() -> None:
    """
    This is a no-op function - the registration happens as soon as the module is imported.

    In some cases, it's still useful to make the import happen, though.

    """
