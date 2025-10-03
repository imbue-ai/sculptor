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
from typing import Any
from typing import Callable
from typing import Collection
from typing import Generator
from typing import Generic
from typing import ParamSpec
from typing import TypeVar

import psycopg
import sentry_sdk
import sqlalchemy
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
from sqlalchemy import UniqueConstraint
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import select
from sqlalchemy.sql.schema import Table

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry import flush_sentry_and_exit_program
from imbue_core.sculptor.telemetry import send_exception_to_posthog
from imbue_core.sculptor.telemetry import with_consent
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.thread_utils import ObservableThread
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
from sculptor.database.utils import is_read_only_sqlite_url
from sculptor.database.utils import maybe_get_db_path
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.primitives.ids import ObjectID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TransactionID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import UserSettingsID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.data_model_service.api import TQ
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.data_types import BaseDataModelTransaction
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
)

TASK_TABLE, TASK_LATEST_TABLE = create_tables(
    to_snake(Task.__name__),
    Task,
    constraints=(
        ForeignKeyConstraint(["parent_task_id"], ["task_latest.object_id"], name="foreign_key_parent_task_id"),
        ForeignKeyConstraint(
            ["project_id"], [f"{PROJECT_LATEST_TABLE.name}.object_id"], name="foreign_key_project_id"
        ),
    ),
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


NOTIFICATION_TABLE, _ = create_tables(
    to_snake(Notification.__name__),
    Notification,
    constraints=(
        ForeignKeyConstraint(["task_id"], [f"{TASK_LATEST_TABLE.name}.object_id"], name="foreign_key_task_id"),
    ),
    # We don't need a latest table for notifications -- editing them would be quite strange
    is_dual_table=False,
)


T = TypeVar("T")
T2 = TypeVar("T2", bound=DatabaseModel)
T3 = TypeVar("T3", bound=Project | UserSettings | Notification)
T4 = TypeVar("T4", bound=Project | UserSettings | Notification | Task)

_WAIT_FOR_LOCK_TIMEOUT_SEC = 10.0


class DatabaseWriteEventData(PosthogEventPayload):
    table_name: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    operation: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    transaction_id: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    model_data: dict = with_consent(
        ConsentLevel.SESSION_RECORDING
    )  # The actual model data, highest level of consent is necessary


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

    def get_projects(self, organization_reference: OrganizationReference | None = None) -> tuple[Project, ...]:
        statement = select(PROJECT_LATEST_TABLE)
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
    def upsert_user_settings(self, user_settings: UserSettings) -> UserSettings:
        return self._upsert_model(user_settings, USER_SETTINGS_TABLE, self.get_user_settings_by_id)

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
    def get_user_settings_by_id(self, user_settings_id: UserSettingsID) -> UserSettings | None:
        statement = select(USER_SETTINGS_LATEST_TABLE).where(
            USER_SETTINGS_LATEST_TABLE.c.object_id == str(user_settings_id)
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
        except (sqlite3.IntegrityError, psycopg.errors.UniqueViolation):
            # If the user settings already exist (e.g. because it was created in another thread), it's fine.
            pass
        user_settings = self.get_user_settings(user_reference)
        assert user_settings is not None
        return user_settings

    def insert_notification(self, notification: Notification) -> Notification:
        self._insert_model(notification, NOTIFICATION_TABLE)
        return notification

    @overwrite_missing_table_error_for_sentry
    def upsert_task(self, task: Task) -> Task:
        return self._upsert_model(task, TASK_TABLE, self.get_task)

    @overwrite_missing_table_error_for_sentry
    def get_task(self, task_id: TaskID) -> Task | None:
        statement = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.object_id == str(task_id))
            .where(TASK_LATEST_TABLE.c.is_deleted == False)
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
        is_archived: bool,
        outcomes: Collection[TaskState] | None = None,
        max_results: int | None = None,
    ) -> tuple[Task, ...]:
        query = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.project_id == str(project_id))
            .where(TASK_LATEST_TABLE.c.is_archived == is_archived)
            .where(TASK_LATEST_TABLE.c.is_deleted == False)
            .order_by(TASK_LATEST_TABLE.c.created_at)
        )
        if outcomes is not None:
            query = query.where(TASK_LATEST_TABLE.c.outcome.in_(outcomes))
        if max_results is not None:
            query = query.limit(max_results)
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def get_all_tasks(self) -> tuple[Task, ...]:
        query = select(TASK_LATEST_TABLE).order_by(TASK_LATEST_TABLE.c.created_at)
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def get_active_tasks(self) -> tuple[Task, ...]:
        query = select(TASK_LATEST_TABLE).where(TASK_LATEST_TABLE.c.is_deleted == False)
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task) for row in result.all())

    def insert_message(self, message: SavedAgentMessage) -> SavedAgentMessage:
        self._insert_model(message, SAVED_AGENT_MESSAGE_TABLE)
        return message

    def get_messages_for_task(self, task_id: TaskID) -> tuple[SavedAgentMessage, ...]:
        query = (
            select(SAVED_AGENT_MESSAGE_TABLE)
            .where(SAVED_AGENT_MESSAGE_TABLE.c.task_id == str(task_id))
            # FIXME: no, this needs to have an auto incrementing id or something, this is too dicey
            .order_by(SAVED_AGENT_MESSAGE_TABLE.c.created_at)
        )
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, SavedAgentMessage) for row in result.all())

    @overwrite_missing_table_error_for_sentry
    def get_latest_tasks_for_user(self, user_reference: UserReference, project_id: ProjectID) -> tuple[Task, ...]:
        """Get all non-deleted tasks for a user in a project."""
        query = (
            select(TASK_LATEST_TABLE)
            .where(TASK_LATEST_TABLE.c.user_reference == str(user_reference))
            .where(TASK_LATEST_TABLE.c.project_id == str(project_id))
            .where(TASK_LATEST_TABLE.c.is_deleted == False)
            .order_by(TASK_LATEST_TABLE.c.created_at.desc())
        )
        result = self.connection.execute(query)
        return tuple(_row_to_pydantic_model(row, Task, prefix="task_latest_") for row in result.all())

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
        # TODO: technically we need to read the value out of the database.
        #  It's a bit tricky because of how the created_at time is set in sqlite.
        #  We can come back to this though
        result = self.connection.execute(statement)
        assert result.rowcount == 1, "Expected exactly one row to be inserted"

        self._updated_models.append((operation, obj))

        return obj


def _row_to_pydantic_model(row: sqlalchemy.Row, model_cls: type[T2], prefix: str = "") -> T2:
    values = {}
    for field_name, field in model_cls.model_fields.items():
        row_value = getattr(row, f"{prefix}{field_name}")
        pydantic_type = field.annotation
        leaf_types = extract_leaf_types(pydantic_type)
        if row_value is not None and any(
            isinstance(leaf_type, type) and issubclass(leaf_type, SerializableModel) for leaf_type in leaf_types
        ):
            # values[field_name] = json.loads(row_value)
            values[field_name] = row_value
            continue
        if row_value is not None and isinstance(row_value, datetime) and row_value.tzinfo is None:
            # For naive datetime objects, assume UTC.
            # (We store stuff as UTC but e.g. sqlite does not support timezones so the values come back as naive.)
            row_value = row_value.replace(tzinfo=timezone.utc)
        values[field_name] = row_value
    return model_cls.model_validate(values)


def _pydantic_model_to_row_values(model: T2) -> dict[str, Any]:
    values = {}
    for field_name, field in model.__class__.model_fields.items():
        value = getattr(model, field_name)
        if isinstance(value, SerializableModel):
            values[field_name] = value.model_dump(mode="json")
        elif isinstance(value, ObjectID):
            values[field_name] = str(value)
        elif type(value) == EmailStr:
            values[field_name] = str(value)
        else:
            values[field_name] = value
    return values


# This is a callback that will be called when a downgrade is detected.
# It should return True if the database initialization should be retried, False otherwise.
# (We cannot easily retry from the high-level bootstrap code because the server.run() invocation leaves a lot of state behind.)
on_downgrade_detected_should_retry: Callable[[str], bool] = lambda database_url: False


def register_on_downgrade_detected_should_retry(callback: Callable[[str], bool]) -> None:
    global on_downgrade_detected_should_retry
    on_downgrade_detected_should_retry = callback


def _initialize_db_and_maybe_resolve_downgrade_if_needed(engine: Engine) -> None:
    try:
        initialize_db(engine)
    except MigrationsFailedError as error:
        if not error.is_likely_a_result_of_sculptor_downgrade:
            raise
        logger.info("Incompatible sculptor downgrade detected!")
        if not on_downgrade_detected_should_retry(str(engine.url)):
            raise
        initialize_db(engine)


# Keep a reference to the lock to prevent garbage collection.
_GLOBAL_SCULPTOR_INSTANCE_LOCK_TO_PREVENT_CONCURRENT_DB_ACCESS: BaseFileLock | None = None


class SQLDataModelService(TaskDataModelService, Generic[TQ]):
    _engine: Engine = PrivateAttr()
    _observers_by_user_reference: dict[UserReference, list[TQ]] = PrivateAttr(default_factory=dict)
    _is_started: bool = PrivateAttr(default=False)
    # Use this flag to skip initialization if the service is running in read-only mode.
    _is_read_only: bool = PrivateAttr(default=False)
    # we track the currently active transactions for debugging -- we want to know what takes a long time when the DB is locked
    _active_transaction_by_id: dict[TransactionID, SQLTransaction] = PrivateAttr(default_factory=dict)
    # ensure that our parent process doesn't disappear. If it does, we must exit
    _parent_watch_thread: ObservableThread | None = PrivateAttr(default=None)

    @classmethod
    def build_from_settings(cls, settings: SculptorSettings) -> "SQLDataModelService":
        # Create directory for SQLite file-based databases if needed
        db_path = maybe_get_db_path(settings.DATABASE_URL)
        if db_path is not None:
            db_dir = db_path.parent
            if not db_dir.exists():
                logger.info("Creating database directory: {}", db_dir)
                db_dir.mkdir(parents=True, exist_ok=True)
        engine = create_new_engine(settings.DATABASE_URL)
        data_model_service = cls()
        data_model_service._engine = engine
        return data_model_service

    def _emit_db_write_telemetry_for_transaction(self, transaction: SQLTransaction) -> None:
        """
        Emit DB_WRITE Posthog events for all models written during this transaction.
        """
        try:
            for operation, model in transaction._updated_models:
                # Create event data with the actual model data included
                event_data = DatabaseWriteEventData(
                    table_name=to_snake(model.__class__.__name__),
                    operation=operation,  # Now correctly uses INSERT or UPDATE
                    transaction_id=str(transaction.transaction_id),
                    model_data=model.model_dump(),  # Include the actual model data
                )

                # Extract task_id from model if it has one (or if it is one)
                task_id = None
                if hasattr(model, "task_id"):
                    model_task_id = getattr(model, "task_id", None)
                    if model_task_id is not None:
                        task_id = str(model_task_id)
                elif type(model) == Task:
                    task_id = str(model.object_id)

                posthog_event = PosthogEventModel[DatabaseWriteEventData](
                    name=SculptorPosthogEvent.DB_WRITE,
                    component=ProductComponent.DATABASE,
                    task_id=task_id,
                    payload=event_data,
                )

                emit_posthog_event(posthog_event)

        except Exception as e:
            # Don't let telemetry errors break the application
            log_exception(e, "Failed to emit DB write telemetry to posthog")

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
                send_exception_to_posthog(error)
                flush_sentry_and_exit_program(SCULPTOR_EXIT_CODE_COULD_NOT_ACQUIRE_LOCK, message)
            # as soon as we've started holding this lock, we need to make sure that we are going to exit if our parent dies
            # this is important because our parent is, in the general case, the electron process
            # if the user hard exits that process, they might not expect that the python server is still running
            self._parent_watch_thread = ObservableThread(
                target=self._watch_parent_process, daemon=True, args=(parent_pid,)
            )
            self._parent_watch_thread.start()

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
            _initialize_db_and_maybe_resolve_downgrade_if_needed(self._engine)
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
                # By now, the user has presumably refused to clear their database.
                # It's an expected case that we don't want to log as an error.
                send_exception_to_posthog(error)
                flush_sentry_and_exit_program(
                    SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR,
                    "Sculptor database is not compatible (have you downgraded Sculptor?). Terminating.",
                )

            logger.error("database startup: failed to run migrations for the newest version. Please contact support.")
            raise

    def _watch_parent_process(self, parent_pid: int) -> None:
        while True:
            time.sleep(_WAIT_FOR_LOCK_TIMEOUT_SEC / 2.2)
            # FIXME(windows): this won't work on windows -- we'll need to check if the parent process exited
            if os.getppid() != parent_pid:
                logger.info("Parent process has exited, so we are exiting too.")
                # note that we VERY SPECIFICALLY DO NOT CALL flush_sentry_and_exit_program
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

    @contextmanager
    def open_task_transaction(self) -> Generator[SQLTransaction, None, None]:
        with self.open_transaction(RequestID(), is_user_request=False) as transaction:
            yield transaction

    @contextmanager
    def open_transaction(
        self, request_id: RequestID, is_user_request: bool = True
    ) -> Generator[SQLTransaction, None, None]:
        if not self._is_started:
            raise AttemptedOperationBeforeStartError(
                "SQLDataModelService must be started before opening transactions."
            )
        transaction_id = TransactionID()
        with sentry_sdk.start_transaction(
            name="SQL Transaction",
            op="db.sql.transaction",
            trace_id=str(transaction_id if request_id is None else request_id),
        ) as _sentry_transaction:
            call_stack = "".join(traceback.format_stack())
            with self._engine.begin() as connection:
                transaction = SQLTransaction(
                    request_id=request_id, connection=connection, transaction_id=transaction_id, call_stack=call_stack
                )
                with logger.contextualize(transaction_id=transaction.transaction_id):
                    # and timestamp and tb
                    self._active_transaction_by_id[transaction_id] = transaction
                    try:
                        yield transaction
                    except OperationalError as e:
                        # when we get a locked error, assemble a bunch of information about the other in-flight transactions to help with debugging
                        if "database is locked" in str(e) and "database is locked" in str(e):
                            transaction_summary = self._get_debug_transaction_summary(transaction)
                            log_exception(
                                e,
                                "Database is locked, inspect extra data to see why",
                                sentry_extra=dict(transaction_summary=transaction_summary),
                            )
                        raise
                    finally:
                        del self._active_transaction_by_id[transaction_id]

        transaction.run_post_commit_hooks()

        self._emit_db_write_telemetry_for_transaction(transaction)

        # Filter database operations to only include observable models (Project, User, Notification)
        # The observer system only cares about these specific model types, not all database operations
        observable_models = []
        for operation, model in transaction.get_updated_models():
            if isinstance(model, (Project, UserSettings, Notification)):
                observable_models.append(model)

        completed_transaction = CompletedTransaction(request_id=request_id, updated_models=tuple(observable_models))

        # ignore read-only requests from tasks
        if not is_user_request and len(completed_transaction.updated_models) == 0:
            return
        # TODO: once we have more than one user, we'll need to filter things down here.
        #  for right now we just send to everyone!
        for user_reference, observers in self._observers_by_user_reference.items():
            for observer in observers:
                observer.put(completed_transaction)

    def _get_debug_transaction_summary(self, transaction: SQLTransaction) -> str:
        now = time.monotonic()
        transaction_summary_entries = [
            f"Took {now - transaction._start_time:.2f}s to run this transaction, which failed:\n{transaction.call_stack}\n"
        ]
        other_transactions = sorted(
            [
                (now - x._start_time, x.call_stack)
                for x in self._active_transaction_by_id.values()
                if x.transaction_id != transaction.transaction_id
            ],
            reverse=True,
        )
        transaction_summary_entries.append(f"{len(other_transactions)} other active transactions:\n")
        for age, stack in other_transactions:
            transaction_summary_entries.append(f"ACTIVE FOR {age:.2f}s:\n{stack}\n")
        transaction_summary = "\n".join(transaction_summary_entries)
        return transaction_summary

    @contextmanager
    def observe_user_changes(
        self, user_reference: UserReference, organization_reference: OrganizationReference, queue: TQ
    ) -> Generator[TQ, None, None]:
        self._observers_by_user_reference[user_reference] = self._observers_by_user_reference.get(
            user_reference, []
        ) + [queue]

        # put the current project and user in the queue
        with self.open_transaction(RequestID()) as transaction:
            user_settings = transaction.get_user_settings(user_reference)
            assert user_settings is not None
            projects = transaction.get_projects(organization_reference)

        existing_models: list[Project | UserSettings | Notification] = [user_settings]
        for project in projects:
            existing_models.append(project)
        queue.put(CompletedTransaction(request_id=None, updated_models=tuple(existing_models)))

        try:
            yield queue
        finally:
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
