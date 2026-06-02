import json
import sqlite3
import threading
import time
import typing
from contextlib import ExitStack
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Generator
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError

from sculptor.foundation.agents.data_types.ids import AgentMessageID
from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.state.messages import ChatInputUserMessage
from sculptor.foundation.state.messages import LLMModel
from sculptor.config.settings import SculptorSettings
from sculptor.database.alembic.json_migrations import get_json_schemas_of_all_nested_models
from sculptor.database.alembic.json_migrations import get_potentially_breaking_changes
from sculptor.database.alembic.migration_test_utils import MigrationTestFixture
from sculptor.database.alembic.migration_test_utils import discover_test_fixtures
from sculptor.database.alembic.utils import get_frozen_database_model_nested_json_schemas
from sculptor.database.automanaged import AUTOMANAGED_MODEL_CLASSES
from sculptor.database.automanaged import OBJECT_ID
from sculptor.database.automanaged import SNAPSHOT_ID
from sculptor.database.core import IN_MEMORY_SQLITE
from sculptor.database.core import METADATA
from sculptor.database.core import create_new_engine
from sculptor.database.core import initialize_db_from_connection
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import MustBeShutDownTaskInputsV1
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import Project
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import DiffStatus
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.primitives.ids import ObjectID
from sculptor.primitives.ids import ObjectSnapshotID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.data_model_service.data_types import ProjectFieldUpdate
from sculptor.services.data_model_service.data_types import WORKSPACE_CREATION_ONLY_FIELDS
from sculptor.services.data_model_service.data_types import WorkspaceFieldUpdate
from sculptor.services.data_model_service.sql_implementation import PROJECT_LATEST_TABLE
from sculptor.services.data_model_service.sql_implementation import PROJECT_TABLE
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService
from sculptor.services.data_model_service.sql_implementation import SQLTransaction
from sculptor.services.data_model_service.sql_implementation import WORKSPACE_LATEST_TABLE
from sculptor.services.data_model_service.sql_implementation import WORKSPACE_TABLE
from sculptor.services.data_model_service.sql_implementation import _UPDATE_FIELDS_PROTECTED_COLUMNS
from sculptor.utils.type_utils import extract_leaf_types


@pytest.fixture
def test_db_service(
    test_settings: SculptorSettings, test_root_concurrency_group: ConcurrencyGroup
) -> Generator[SQLDataModelService, None, None]:
    service = SQLDataModelService.build_from_settings(
        test_settings, test_root_concurrency_group.make_concurrency_group("data_model_service")
    )
    with service.run():
        yield service


@pytest.fixture
def test_db_service_with_user_organization_and_project(
    test_db_service: SQLDataModelService,
) -> tuple[SQLDataModelService, UserReference, OrganizationReference, Project]:
    user_reference = UserReference("authentik-dummy-id")
    organization_reference = OrganizationReference("authentik-dummy-organization-id")
    with test_db_service.open_transaction(RequestID()) as transaction:
        project = Project(object_id=ProjectID(), name="Example Project", organization_reference=organization_reference)
        transaction.upsert_project(project)
        transaction.get_or_create_user_settings(user_reference)
    return (test_db_service, user_reference, organization_reference, project)


def get_simple_agent_task(
    code_directory: Path,
    user_reference: UserReference,
    organization_reference: OrganizationReference,
    project: Project,
) -> Task:
    task = Task(
        object_id=TaskID(),
        max_seconds=30,
        input_data=AgentTaskInputsV2(
            agent_config=HelloAgentConfig(),
            git_hash="HEAD",
            system_prompt=None,
        ),
        organization_reference=organization_reference,
        user_reference=user_reference,
        project_id=project.object_id,
    )
    return task


def get_simple_non_agent_task(
    code_directory: Path,
    user_reference: UserReference,
    organization_reference: OrganizationReference,
    project: Project,
) -> Task:
    task = Task(
        object_id=TaskID(),
        max_seconds=30,
        input_data=MustBeShutDownTaskInputsV1(),
        organization_reference=organization_reference,
        user_reference=user_reference,
        project_id=project.object_id,
    )
    return task


def test_write_and_read_task(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    task_id = task.object_id
    with service.open_transaction(RequestID()) as transaction:
        maybe_task = transaction.get_task(task_id)
        assert maybe_task is None, "Expected no task to exist before insertion."
    with service.open_transaction(RequestID()) as transaction:
        inserted_task = transaction.upsert_task(task)
        for field in Task.model_fields:
            assert getattr(inserted_task, field) == getattr(task, field), f"Expected {field} to be the same."
    with service.open_transaction(RequestID()) as transaction:
        retrieved_task = transaction.get_task(task_id)
        assert retrieved_task == inserted_task, "Expected the retrieved task to match the inserted task."


def test_get_active_tasks(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    agent_task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    non_agent_task = get_simple_non_agent_task(tmp_path, user_reference, organization_reference, project)
    with service.open_task_transaction() as transaction:
        transaction.upsert_task(agent_task)
        transaction.upsert_task(non_agent_task)
    with service.open_task_transaction() as transaction:
        tasks = transaction.get_active_tasks()
        assert len(tasks) == 2
        tasks = transaction.get_active_tasks(input_data_classes=(type(agent_task.input_data),))
        assert len(tasks) == 1
        assert tasks[0].object_id == agent_task.object_id
        tasks = transaction.get_active_tasks(input_data_classes=(type(non_agent_task.input_data),))
        assert len(tasks) == 1
        assert tasks[0].object_id == non_agent_task.object_id


def test_get_active_tasks_excludes_deleting_tasks(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """get_active_tasks should exclude tasks with is_deleting=True, matching the behavior of get_tasks_for_user."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    normal_task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    deleting_task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    deleting_task = deleting_task.evolve(deleting_task.ref().is_deleting, True)
    with service.open_task_transaction() as transaction:
        transaction.upsert_task(normal_task)
        transaction.upsert_task(deleting_task)
    with service.open_task_transaction() as transaction:
        tasks = transaction.get_active_tasks()
        assert len(tasks) == 1
        assert tasks[0].object_id == normal_task.object_id


def test_get_tasks_for_project(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    agent_task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    non_agent_task = get_simple_non_agent_task(tmp_path, user_reference, organization_reference, project)
    with service.open_task_transaction() as transaction:
        transaction.upsert_task(agent_task)
        transaction.upsert_task(non_agent_task)
    with service.open_task_transaction() as transaction:
        tasks = transaction.get_tasks_for_project(project_id=project.object_id)
        assert len(tasks) == 2
        tasks = transaction.get_tasks_for_project(project_id=ProjectID())
        assert len(tasks) == 0
        tasks = transaction.get_active_tasks(input_data_classes=(type(agent_task.input_data),))
        assert len(tasks) == 1
        assert tasks[0].object_id == agent_task.object_id
        tasks = transaction.get_active_tasks(
            input_data_classes=(type(non_agent_task.input_data), type(agent_task.input_data))
        )
        assert len(tasks) == 2


def test_get_tasks_for_project_excludes_deleting_tasks(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """get_tasks_for_project should exclude is_deleting tasks so the task spawner doesn't pick them up."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    normal_task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    deleting_task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    deleting_task = deleting_task.evolve(deleting_task.ref().is_deleting, True)
    with service.open_task_transaction() as transaction:
        transaction.upsert_task(normal_task)
        transaction.upsert_task(deleting_task)
    with service.open_task_transaction() as transaction:
        tasks = transaction.get_tasks_for_project(project_id=project.object_id)
        assert len(tasks) == 1
        assert tasks[0].object_id == normal_task.object_id


def test_foreign_constraints_are_being_enforced(test_db_service: SQLDataModelService, tmp_path: Path) -> None:
    message_id = AgentMessageID()
    saved_agent_message = SavedAgentMessage.build(
        message=ChatInputUserMessage(message_id=message_id, text="Hello, world!", model_name=LLMModel.CLAUDE_4_SONNET),
        task_id=TaskID(),
    )
    with pytest.raises(IntegrityError):
        with test_db_service.open_transaction(RequestID()) as transaction:
            transaction.insert_message(saved_agent_message)


BUMP_MIGRATIONS_COMMAND = "uv run --project sculptor python sculptor/sculptor/scripts/bump_migrations.py"


def test_there_are_no_missing_sql_schema_migrations(test_db_service: SQLDataModelService) -> None:
    migration_context = MigrationContext.configure(connection=test_db_service._engine.connect())
    differences = compare_metadata(migration_context, METADATA)
    assert len(differences) == 0, "\n".join(
        [
            f"There are missing migrations in the database schema compared to the metadata. Please run `{BUMP_MIGRATIONS_COMMAND}`.",
            "\n -".join(differences),
        ]
    )


def test_missing_sql_schema_migrations_detection_works(test_db_service: SQLDataModelService, tmp_path: Path) -> None:
    with test_db_service._engine.begin() as connection:
        connection.execute(text("CREATE TABLE new_table (id INTEGER PRIMARY KEY)"))
    migration_context = MigrationContext.configure(connection=test_db_service._engine.connect())
    differences = compare_metadata(migration_context, METADATA)
    assert len(differences) > 0, "We should have detected the missing migration for the new table."


def test_there_are_no_missing_json_schema_migrations() -> None:
    frozen_schemas = get_frozen_database_model_nested_json_schemas()
    latest_schemas = get_json_schemas_of_all_nested_models(tuple(AUTOMANAGED_MODEL_CLASSES))
    potentially_breaking_changes = get_potentially_breaking_changes(frozen_schemas, latest_schemas)
    assert len(potentially_breaking_changes) == 0, "\n".join(
        [
            f"There are missing migrations in the JSON schemas compared to the frozen schemas. Please run `{BUMP_MIGRATIONS_COMMAND}`.",
            "\n -".join(potentially_breaking_changes),
        ]
    )


# ============================================================================
# MIGRATION CORRECTNESS TESTS
# These tests verify that the Alembic migration chain produces a correct
# schema and that triggers work properly after migration.
# ============================================================================


def _get_schema_info(engine) -> dict[str, Any]:  # noqa: ANN001
    """Extract a normalized schema description from a database engine for comparison."""
    inspector = inspect(engine)
    schema: dict[str, Any] = {}
    for table_name in sorted(inspector.get_table_names()):
        if table_name == "alembic_version":
            continue
        columns = {}
        for col in inspector.get_columns(table_name):
            columns[col["name"]] = {
                "type": str(col["type"]),
                "nullable": col["nullable"],
            }
        pk = inspector.get_pk_constraint(table_name)
        fks = [
            {
                "constrained_columns": fk["constrained_columns"],
                "referred_table": fk["referred_table"],
                "referred_columns": fk["referred_columns"],
            }
            for fk in inspector.get_foreign_keys(table_name)
        ]
        unique_constraints = [
            {"columns": sorted(uc["column_names"])} for uc in inspector.get_unique_constraints(table_name)
        ]
        schema[table_name] = {
            "columns": columns,
            "primary_key": sorted(pk["constrained_columns"]) if pk else [],
            "foreign_keys": sorted(fks, key=lambda fk: str(fk["constrained_columns"])),
            "unique_constraints": sorted(unique_constraints, key=lambda uc: str(uc["columns"])),
        }
    return schema


def test_migration_chain_produces_correct_schema() -> None:
    """Verify that running all migrations from scratch produces the same schema as creating tables directly.

    This catches migrations that produce a schema divergent from the codebase's expectations:
    missing columns, wrong types, dropped constraints, etc.
    """
    from sculptor.services.data_model_service.sql_implementation import register_all_tables

    register_all_tables()

    # DB-A: fresh schema created directly from model definitions (the "ground truth")
    engine_fresh = create_new_engine(IN_MEMORY_SQLITE)
    METADATA.create_all(engine_fresh)
    schema_fresh = _get_schema_info(engine_fresh)

    # DB-B: schema produced by running all migrations from initial to head
    engine_migrated = create_new_engine(IN_MEMORY_SQLITE)
    with engine_migrated.begin() as connection:
        initialize_db_from_connection(connection, IN_MEMORY_SQLITE)
    schema_migrated = _get_schema_info(engine_migrated)

    # Compare table sets
    fresh_tables = set(schema_fresh.keys())
    migrated_tables = set(schema_migrated.keys())
    assert fresh_tables == migrated_tables, (
        f"Table mismatch.\n"
        f"  Only in fresh (not produced by migrations): {fresh_tables - migrated_tables}\n"
        f"  Only in migrated (not in model definitions): {migrated_tables - fresh_tables}"
    )

    # Compare each table's structure
    differences: list[str] = []
    for table_name in sorted(fresh_tables):
        fresh_table = schema_fresh[table_name]
        migrated_table = schema_migrated[table_name]

        if fresh_table["columns"] != migrated_table["columns"]:
            differences.append(
                f"Table '{table_name}' columns differ:\n"
                f"  fresh:    {fresh_table['columns']}\n"
                f"  migrated: {migrated_table['columns']}"
            )
        if fresh_table["primary_key"] != migrated_table["primary_key"]:
            differences.append(
                f"Table '{table_name}' primary key differs:\n"
                f"  fresh:    {fresh_table['primary_key']}\n"
                f"  migrated: {migrated_table['primary_key']}"
            )
        if fresh_table["foreign_keys"] != migrated_table["foreign_keys"]:
            differences.append(
                f"Table '{table_name}' foreign keys differ:\n"
                f"  fresh:    {fresh_table['foreign_keys']}\n"
                f"  migrated: {migrated_table['foreign_keys']}"
            )
        if fresh_table["unique_constraints"] != migrated_table["unique_constraints"]:
            differences.append(
                f"Table '{table_name}' unique constraints differ:\n"
                f"  fresh:    {fresh_table['unique_constraints']}\n"
                f"  migrated: {migrated_table['unique_constraints']}"
            )

    assert len(differences) == 0, (
        "Migration chain produces a schema that differs from creating tables directly:\n" + "\n".join(differences)
    )


def _generate_synthetic_value(field_name: str, pydantic_type: type) -> Any:
    """Generate a synthetic value for a Pydantic model field based on its type."""
    leaf_types = extract_leaf_types(pydantic_type)
    non_none_types = [t for t in leaf_types if t is not type(None)]
    if not non_none_types:
        return None
    actual_type = non_none_types[0]
    if not isinstance(actual_type, type):
        return json.dumps({})
    if issubclass(actual_type, ObjectID):
        return str(actual_type())
    if issubclass(actual_type, SerializableModel):
        return json.dumps({"object_type": "synthetic_test_data"})
    if issubclass(actual_type, datetime):
        return "2025-01-01T00:00:00+00:00"
    if issubclass(actual_type, bool):
        return False
    if issubclass(actual_type, int):
        return 42
    if issubclass(actual_type, float):
        return 3.14
    if issubclass(actual_type, str):
        return f"test_{field_name}"
    return f"test_{field_name}"


def test_triggers_work_after_migration() -> None:
    """Verify that after running all migrations and applying triggers, the dual-table pattern works.

    For each model with a dual table, inserting into the snapshots table should cause the row
    to appear in the _latest table via triggers.
    """
    from pydantic.alias_generators import to_snake

    from sculptor.services.data_model_service.sql_implementation import register_all_tables

    register_all_tables()

    # Create engine without the FK enforcement listener — we're testing trigger behavior,
    # not referential integrity. FK constraints on _latest tables would otherwise require
    # inserting parent records in dependency order, which is unrelated to what we're testing.
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(IN_MEMORY_SQLITE, poolclass=StaticPool, connect_args={"check_same_thread": False})

    with engine.begin() as connection:
        initialize_db_from_connection(connection, IN_MEMORY_SQLITE)

        triggers_info = METADATA.info.get("triggers", {})
        tables_with_triggers = set(triggers_info.keys())
        assert len(tables_with_triggers) > 0, "Expected at least one table with triggers"

        for model_cls in AUTOMANAGED_MODEL_CLASSES:
            table_name = to_snake(model_cls.__name__)

            if table_name not in tables_with_triggers:
                continue

            latest_table_name = f"{table_name}_latest"

            # Build column values from the model's field definitions
            field_values: dict[str, Any] = {}
            for field_name, field in model_cls.model_fields.items():
                field_values[field_name] = _generate_synthetic_value(field_name, field.annotation)

            # Insert a row into the snapshots table
            snapshot_id_1 = str(ObjectSnapshotID())
            columns = [SNAPSHOT_ID] + list(field_values.keys())
            placeholders = ", ".join([f":{c}" for c in columns])
            column_names = ", ".join(columns)
            insert_params = {SNAPSHOT_ID: snapshot_id_1, **field_values}

            connection.execute(
                text(f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"),
                insert_params,
            )

            # Verify the row appeared in the _latest table
            result = connection.execute(
                text(f"SELECT * FROM {latest_table_name} WHERE {OBJECT_ID} = :oid"),
                {"oid": field_values[OBJECT_ID]},
            )
            rows = result.fetchall()
            assert len(rows) == 1, (
                f"Expected 1 row in {latest_table_name} after insert into {table_name}, got {len(rows)}"
            )

            # Insert a second row with the same object_id but different snapshot_id
            # to verify upsert behavior in _latest
            insert_params[SNAPSHOT_ID] = str(ObjectSnapshotID())

            connection.execute(
                text(f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"),
                insert_params,
            )

            # Verify still exactly one row in _latest for this object_id
            result = connection.execute(
                text(f"SELECT * FROM {latest_table_name} WHERE {OBJECT_ID} = :oid"),
                {"oid": field_values[OBJECT_ID]},
            )
            rows = result.fetchall()
            assert len(rows) == 1, (
                f"Expected 1 row in {latest_table_name} after second insert into {table_name}, got {len(rows)}"
            )


def _get_migration_fixtures() -> list[MigrationTestFixture]:
    """Discover all migration test fixtures for parametrized testing."""
    return discover_test_fixtures()


# ============================================================================
# MIGRATION FIXTURE TESTS
# These tests ensure every migration has a test fixture and that
# each fixture's seed/verify logic runs successfully.
# ============================================================================


def test_every_migration_has_a_test_fixture() -> None:
    """Enforce that every migration file has a companion test fixture file."""
    from sculptor.database.alembic.migration_test_utils import get_all_migration_revision_ids
    from sculptor.database.alembic.migration_test_utils import get_all_test_fixture_revision_ids

    migration_ids = get_all_migration_revision_ids()
    fixture_ids = get_all_test_fixture_revision_ids()

    missing = migration_ids - fixture_ids
    assert not missing, (
        f"The following migrations are missing test fixtures: {sorted(missing)}. "
        f"Each migration must have a companion test_<revision_id>.py file "
        f"in sculptor/database/alembic/versions/."
    )


@pytest.mark.parametrize(
    "fixture",
    _get_migration_fixtures(),
    ids=lambda f: f.revision,
)
def test_migration_fixture(fixture: MigrationTestFixture) -> None:
    """Run a single migration test fixture: seed data, apply migration, verify."""
    from sculptor.database.alembic.migration_test_utils import run_migration_fixture_test

    run_migration_fixture_test(fixture)


# ============================================================================
# OBSERVER BEHAVIOR TESTS
# These tests verify the current behavior by mocking observer notifications
# via queue.put() calls. This ensures refactoring doesn't break existing
# functionality.
# ============================================================================


def test_observer_notification_project_upsert(test_db_service: SQLDataModelService) -> None:
    """Test that Project upsert operations trigger observer notifications."""
    organization_reference = OrganizationReference("test-org-id")
    user_reference = UserReference("test-user-id")
    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.get_or_create_user_settings(user_reference)

    project = Project(object_id=ProjectID(), name="Test Project", organization_reference=organization_reference)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with test_db_service.observe_user_changes(user_reference, organization_reference, mock_queue):
        # The observe() context manager puts initial state, so reset the mock
        mock_queue.reset_mock()

        with test_db_service.open_transaction(RequestID()) as transaction:
            transaction.upsert_project(project)

        # Verify that the observer was called with a CompletedTransaction containing the project
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        assert len(completed_transaction.updated_models) == 1
        assert completed_transaction.updated_models[0] == project


def test_observer_notification_tolerates_observer_unregistering_during_notification(
    test_db_service: SQLDataModelService,
) -> None:
    """An observer unregistering during notification must not break the other observers.

    Regression test: observers are unregistered from websocket handler threads
    (on disconnect) while ``open_transaction`` iterates them from request
    threads, which raised ``RuntimeError: dictionary changed size during
    iteration`` and turned unrelated API requests into 500s.
    """
    organization_reference = OrganizationReference("test-org-id")
    first_user_reference = UserReference("test-user-id-1")
    second_user_reference = UserReference("test-user-id-2")
    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.get_or_create_user_settings(first_user_reference)
        transaction.get_or_create_user_settings(second_user_reference)

    second_observation = ExitStack()
    second_user_queue = MagicMock()

    class UnregisterOtherObserverQueue:
        """Queue whose put() unregisters the second user's observer, like a websocket disconnect."""

        def put(self, item: CompletedTransaction) -> None:
            second_observation.close()

    with test_db_service.observe_user_changes(
        first_user_reference, organization_reference, UnregisterOtherObserverQueue()
    ):
        # The with-block guarantees the second observer is unregistered even if
        # the transaction below raises before the first observer's put() fires.
        with second_observation:
            second_observation.enter_context(
                test_db_service.observe_user_changes(second_user_reference, organization_reference, second_user_queue)
            )
            second_user_queue.reset_mock()

            project = Project(
                object_id=ProjectID(), name="Test Project", organization_reference=organization_reference
            )
            with test_db_service.open_transaction(RequestID()) as transaction:
                transaction.upsert_project(project)

            # Notification must continue past the mid-loop unregistration: the
            # second observer was in the registry when the transaction
            # committed, so it still receives the notification.
            second_user_queue.put.assert_called_once()
            assert second_user_queue.put.call_args[0][0].updated_models == (project,)


def test_observer_notification_project_update_upsert(test_db_service: SQLDataModelService) -> None:
    """Test that updating an existing Project via upsert triggers observer notifications."""
    user_reference = UserReference("test-user-id")
    organization_reference = OrganizationReference("test-org-id")
    project = Project(object_id=ProjectID(), name="Test Project", organization_reference=organization_reference)
    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.get_or_create_user_settings(user_reference)
        transaction.upsert_project(project)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with test_db_service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        # Update the project to trigger a notification
        project_updated = project.model_copy(update={"name": "Updated Project"})
        with test_db_service.open_transaction(RequestID()) as transaction:
            transaction.upsert_project(project_updated)

        # Verify that the observer was called with a CompletedTransaction containing the project
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        assert len(completed_transaction.updated_models) == 1
        assert completed_transaction.updated_models[0] == project_updated


def test_observer_notification_notification_insert(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that Notification insert operations trigger observer notifications."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            transaction.upsert_task(task)
            notification = Notification(
                object_id=NotificationID(),
                user_reference=user_reference,
                task_id=task.object_id,
                message="Test notification",
            )
            transaction.insert_notification(notification)

        # Verify that the observer was called with a CompletedTransaction containing only the notification
        # (Task should NOT be included in observer notifications)
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        assert len(completed_transaction.updated_models) == 1
        assert completed_transaction.updated_models[0] == notification


def test_observer_notification_task_upsert_NOT_observed(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that Task upsert operations do NOT trigger observer notifications (current behavior)."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            transaction.upsert_task(task)

        # Task operations trigger an empty CompletedTransaction (with no models in it)
        # This is still a notification to observers, but without any models to observe
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]
        assert len(completed_transaction.updated_models) == 0  # No models should be included


def test_observer_notification_saved_agent_message_insert_NOT_observed(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that SavedAgentMessage insert operations do NOT trigger observer notifications."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            transaction.upsert_task(task)

            message_id = AgentMessageID()
            message = SavedAgentMessage.build(
                message=ChatInputUserMessage(
                    message_id=message_id, text="Test message", model_name=LLMModel.CLAUDE_4_SONNET
                ),
                task_id=task.object_id,
            )
            transaction.insert_message(message)

        # SavedAgentMessage operations don't add models to observer notifications,
        # but Task operations trigger an empty CompletedTransaction
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]
        assert len(completed_transaction.updated_models) == 0  # No models should be included


def test_observer_notification_mixed_operations_behavior(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that observers only receive notifications for models that should be observed."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            # Mix of observed and non-observed operations
            # Note: project already exists, so we need to modify it to get an observer notification
            project_updated = project.model_copy(update={"name": "Updated Project"})
            transaction.upsert_project(project_updated)  # Should be observed (UPDATE)

            transaction.upsert_task(task)  # Should NOT be observed

            notification = Notification(
                object_id=NotificationID(),
                user_reference=user_reference,
                task_id=task.object_id,
                message="Test notification",
            )
            transaction.insert_notification(notification)  # Should be observed

        # Verify that the observer was called with a CompletedTransaction containing only observed models
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        # Only observed models should be in the completed transaction
        assert len(completed_transaction.updated_models) == 2  # project, notification
        model_types = [type(model).__name__ for model in completed_transaction.updated_models]
        assert "Project" in model_types
        assert "Notification" in model_types
        assert "Task" not in model_types  # Task should NOT be included


def _slow_transaction_thread(service: SQLDataModelService, user_reference: UserReference) -> None:
    with service.open_transaction(RequestID()) as transaction:
        time.sleep(5)
        _user_settings = transaction.get_user_settings(user_reference)


def test_debugging_report_from_concurrent_transactions(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    # start the background thread:
    thread = threading.Thread(target=_slow_transaction_thread, args=(service, user_reference))
    thread.start()
    time.sleep(1)  # give it a moment to start and hold the transaction open
    try:
        with expect_exact_logged_errors(["Database is locked, inspect extra data to see why"]):
            # now open a transaction in the main thread, which should detect the concurrent transaction:
            with service.open_transaction(RequestID()) as transaction:
                _user_settings = transaction.get_user_settings(user_reference)
                raise OperationalError(
                    statement="TEST", params={}, orig=sqlite3.OperationalError("database is locked")
                )
    except OperationalError:
        pass
    thread.join()


def test_lock_debug_logging_on_begin_immediate_failure(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """``BEGIN IMMEDIATE`` raising "database is locked" hits the same
    lock-debug log path as the deferred case (SCU-536).

    The connection-acquisition error in ``_begin_immediate_connection.__enter__``
    used to escape ``open_transaction``'s handler because it landed on the
    inner ``with`` block's entry, before the existing ``except OperationalError``
    branch.
    """
    service, _user_reference, _organization_reference, _project = test_db_service_with_user_organization_and_project

    @contextmanager
    def fail_with_database_locked() -> Generator[None, None, None]:
        raise OperationalError(
            statement="BEGIN IMMEDIATE", params={}, orig=sqlite3.OperationalError("database is locked")
        )
        yield  # pragma: no cover  # required so this stays a generator function

    with patch.object(service, "_begin_immediate_connection", fail_with_database_locked):
        try:
            with expect_exact_logged_errors(["Database is locked, inspect extra data to see why"]):
                with service.open_transaction(RequestID(), immediate=True):
                    pass
        except OperationalError:
            pass


# ============================================================================
# WORKSPACE STREAMING TESTS
# These tests verify workspace changes are tracked and streamed correctly.
# ============================================================================


def test_observer_notification_workspace_upsert(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Test that Workspace upsert operations trigger observer notifications."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project

    workspace = Workspace(
        object_id=WorkspaceID(),
        project_id=project.object_id,
        organization_reference=organization_reference,
        description="Test Workspace",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        # The observe() context manager puts initial state, so reset the mock
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            transaction.upsert_workspace(workspace)

        # Verify that the observer was called with a CompletedTransaction containing the workspace
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        assert len(completed_transaction.updated_models) == 1
        assert completed_transaction.updated_models[0] == workspace


def test_observer_notification_workspace_update(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Test that Workspace update operations trigger observer notifications."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project

    workspace = Workspace(
        object_id=WorkspaceID(),
        project_id=project.object_id,
        organization_reference=organization_reference,
        description="Test Workspace",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )

    # First, create the workspace
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_workspace(workspace)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        # Update the workspace
        workspace_updated = workspace.model_copy(update={"description": "Updated Workspace Description"})
        with service.open_transaction(RequestID()) as transaction:
            transaction.upsert_workspace(workspace_updated)

        # Verify that the observer was called with a CompletedTransaction containing the updated workspace
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        assert len(completed_transaction.updated_models) == 1
        assert completed_transaction.updated_models[0] == workspace_updated


def test_observe_user_changes_includes_workspaces_in_initial_state(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Test that observe_user_changes includes workspaces in the initial state dump."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project

    # Create a workspace before subscribing
    workspace = Workspace(
        object_id=WorkspaceID(),
        project_id=project.object_id,
        organization_reference=organization_reference,
        description="Test Workspace",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_workspace(workspace)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        # The observe_user_changes method explicitly puts initial state (including workspaces) on the queue.
        # The initial state dump has request_id=None.
        # Note: The workspace upsert above may also trigger a separate notification (with a request_id).
        initial_calls = [c for c in mock_queue.put.call_args_list if c[0][0].request_id is None]
        assert len(initial_calls) >= 1, "Expected at least one initial state call (request_id=None)"
        initial_transaction = initial_calls[0][0][0]

        # Verify the workspace is in the initial state (along with user_settings and project)
        workspace_models = [m for m in initial_transaction.updated_models if isinstance(m, Workspace)]
        assert len(workspace_models) == 1
        assert workspace_models[0] == workspace


def test_workspaces_filtered_by_organization(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Test that workspaces are filtered by organization in observe_user_changes."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project

    # Create a workspace in the user's organization
    workspace_in_org = Workspace(
        object_id=WorkspaceID(),
        project_id=project.object_id,
        organization_reference=organization_reference,
        description="Workspace in org",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )

    # Create a workspace in a different organization
    other_org = OrganizationReference("other-organization")
    other_project = Project(
        object_id=ProjectID(),
        name="Other Project",
        organization_reference=other_org,
    )
    workspace_other_org = Workspace(
        object_id=WorkspaceID(),
        project_id=other_project.object_id,
        organization_reference=other_org,
        description="Workspace in other org",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )

    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_project(other_project)
        transaction.upsert_workspace(workspace_in_org)
        transaction.upsert_workspace(workspace_other_org)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        completed_transaction = mock_queue.put.call_args[0][0]

        # Verify only the workspace in the user's organization is included
        workspace_models = [m for m in completed_transaction.updated_models if isinstance(m, Workspace)]
        assert len(workspace_models) == 1
        assert workspace_models[0] == workspace_in_org


# ============================================================================
# SCU-168 — defense-in-depth tests for ``immediate=True`` on writer
# transactions in the workspace soft-delete race.
#
# The bug: a slow read-then-write transaction (refresh_workspace_diff's
# READY block) could revive a workspace that a concurrent transaction had
# soft-deleted, because the in-memory ``Workspace`` carried a stale
# ``is_deleted=False`` from before the delete.
#
# Two layered defenses currently apply:
#   1. ``Workspace.is_deleted`` is a monotonic column.  The
#      ``BEFORE INSERT`` trigger does
#      ``is_deleted = MAX(latest.is_deleted, excluded.is_deleted)``, so
#      a full-object upsert with stale ``is_deleted=False`` cannot flip
#      the latched value back to False — *if* the trigger's read of
#      ``latest.is_deleted`` reflects the deleter's commit.  Under
#      pysqlite's auto-BEGIN-on-first-DML behavior this is the case in
#      practice, but the SCU-168 ticket documents that the guarantee may
#      not hold across all WAL interleavings.
#   2. ``immediate=True`` on the refresher's transaction acquires the
#      writer slot at BEGIN time, serializing all writers.  Either the
#      deleter waits for the refresher to commit (so the delete happens
#      after), or the refresher's snapshot already includes the deleter's
#      commit (so ``get_workspace`` returns None and the application's
#      short-circuit guard fires).
#
# These tests verify property (2) — they exercise the IMMEDIATE
# serialization mechanism that ``refresh_workspace_diff`` now relies on.
# ============================================================================


def _seed_workspace(
    service: SQLDataModelService,
    project_id: ProjectID,
    organization_reference: OrganizationReference,
) -> WorkspaceID:
    workspace = Workspace(
        object_id=WorkspaceID(),
        project_id=project_id,
        organization_reference=organization_reference,
        description="seed",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_workspace(workspace)
    return workspace.object_id


def test_immediate_transaction_blocks_concurrent_deleter_until_commit(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """SCU-168: with ``immediate=True``, concurrent writers are serialized.

    The refresher acquires the writer slot at transaction start.  The deleter
    must wait until the refresher commits before its own ``BEGIN IMMEDIATE``
    can succeed.  After both finish, the workspace stays deleted — the
    refresher's full-object upsert (which carries is_deleted=False from a
    pre-delete read) cannot revert the delete because the delete commits
    *after* the refresher's commit.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    refresher_holds_writer = threading.Event()
    refresher_may_proceed = threading.Event()
    deleter_done = threading.Event()

    def refresher() -> None:
        with service.open_transaction(RequestID(), immediate=True) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None
            refresher_holds_writer.set()
            # Hold the writer slot so the deleter has to wait.
            refresher_may_proceed.wait(timeout=5)
            # Upsert with the in-memory copy (is_deleted=False).  Without
            # IMMEDIATE-driven serialization this would be the upsert that
            # could revive a concurrently-deleted workspace.
            updated = workspace.evolve(workspace.ref().description, "refreshed")
            transaction.upsert_workspace(updated)

    def deleter() -> None:
        refresher_holds_writer.wait(timeout=2)
        # This BEGIN IMMEDIATE blocks until the refresher commits.
        with service.open_transaction(RequestID(), immediate=True) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None, (
                "Deleter should see the workspace after refresher's commit (refresher only changed description, not is_deleted)."
            )
            transaction.upsert_workspace(workspace.evolve(workspace.ref().is_deleted, True))
        deleter_done.set()

    refresher_thread = threading.Thread(target=refresher)
    deleter_thread = threading.Thread(target=deleter)
    refresher_thread.start()
    deleter_thread.start()

    # Confirm the deleter is actually blocked behind the refresher's writer slot.
    refresher_holds_writer.wait(timeout=2)
    assert not deleter_done.is_set(), "Deleter should be blocked until refresher commits"

    refresher_may_proceed.set()
    refresher_thread.join(timeout=10)
    deleter_thread.join(timeout=10)
    assert not refresher_thread.is_alive()
    assert not deleter_thread.is_alive()

    # Final state: workspace is deleted.  The refresher's ``description="refreshed"``
    # snapshot upsert ran before the deleter's ``is_deleted=True`` upsert, so
    # the latter wins and the row stays deleted.
    with service.open_transaction(RequestID()) as transaction:
        assert transaction.get_workspace(workspace_id) is None


def test_immediate_transaction_sees_concurrent_delete_in_snapshot(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """SCU-168 (other interleaving): if a delete commits before the refresher
    starts its IMMEDIATE txn, the refresher's snapshot reflects the delete
    and the application-level ``if workspace is None: return`` guard fires.

    Without IMMEDIATE, the refresher's snapshot under WAL DEFERRED can lag
    behind the deleter's commit even when the deleter committed first,
    causing ``get_workspace`` to return non-None and the upsert to revive
    the workspace.  With IMMEDIATE the snapshot is taken after the writer
    slot is held, so it always reflects all prior commits.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    # Capture an in-memory copy of the workspace as the refresher would
    # have read it before the delete.
    with service.open_transaction(RequestID()) as transaction:
        stale_workspace = transaction.get_workspace(workspace_id)
        assert stale_workspace is not None

    # Deleter runs to completion first.
    with service.open_transaction(RequestID(), immediate=True) as transaction:
        workspace = transaction.get_workspace(workspace_id)
        assert workspace is not None
        transaction.upsert_workspace(workspace.evolve(workspace.ref().is_deleted, True))

    # Refresher opens an IMMEDIATE txn after the delete and re-reads.
    # ``get_workspace`` must return None because the snapshot is post-delete.
    with service.open_transaction(RequestID(), immediate=True) as transaction:
        re_read = transaction.get_workspace(workspace_id)
        assert re_read is None, "Refresher should not see deleted workspace via get_workspace"
        # Caller would short-circuit at this point; we don't upsert.

    # Sanity: the workspace really is deleted, even from a fresh read.
    with service.open_transaction(RequestID()) as transaction:
        assert transaction.get_workspace(workspace_id) is None


def test_immediate_transactions_serialize_observably(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Behavioral check: ``immediate=True`` writers serialize from BEGIN to COMMIT.

    Two threads each open a transaction, sleep ``HOLD_SECONDS`` to simulate
    work, and write.  With DEFERRED, both can be in their txns in parallel
    (they only contend for the writer lock at the actual INSERT, briefly).
    With IMMEDIATE, the second thread blocks at BEGIN until the first
    commits, so total wall time is at least ``2 * HOLD_SECONDS``.

    This is the property ``refresh_workspace_diff`` relies on: while one
    refresher holds an IMMEDIATE writer slot, a concurrent delete txn that
    also opens IMMEDIATE cannot interleave with it.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)
    HOLD_SECONDS = 0.3

    def writer(immediate: bool) -> None:
        with service.open_transaction(RequestID(), immediate=immediate) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None
            time.sleep(HOLD_SECONDS)
            transaction.upsert_workspace(workspace.evolve(workspace.ref().description, "modified"))

    def run_pair(immediate: bool) -> float:
        start = time.monotonic()
        threads = [threading.Thread(target=writer, args=(immediate,)) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive()
        return time.monotonic() - start

    # Sanity: both modes leave the workspace existing.
    immediate_elapsed = run_pair(immediate=True)
    with service.open_transaction(RequestID()) as transaction:
        assert transaction.get_workspace(workspace_id) is not None

    deferred_elapsed = run_pair(immediate=False)
    with service.open_transaction(RequestID()) as transaction:
        assert transaction.get_workspace(workspace_id) is not None

    # Two IMMEDIATE writers must serialize: total wall time >= 2 * hold.
    # Allow some tolerance for jitter but stay strictly above 1 * hold so
    # the assertion fails clearly if serialization regresses.
    assert immediate_elapsed >= 2 * HOLD_SECONDS * 0.85, (
        f"IMMEDIATE writers should serialize: expected ~>={2 * HOLD_SECONDS}s, got {immediate_elapsed:.3f}s"
    )

    # And IMMEDIATE must measurably differ from DEFERRED — DEFERRED writers
    # overlap their work, IMMEDIATE writers stack.  Use a generous gap so
    # this isn't fragile under load.
    assert immediate_elapsed > deferred_elapsed + HOLD_SECONDS * 0.5, (
        f"IMMEDIATE should be observably slower than DEFERRED: immediate={immediate_elapsed:.3f}s, deferred={deferred_elapsed:.3f}s"
    )


# ============================================================================
# Lost-update regression: full-object upsert can clobber a concurrent PATCH
# on an unrelated field.
#
# Scenario: a user closes a workspace tab (PATCH ``is_open=False``) while a
# background diff refresher already holds an in-memory ``Workspace`` from
# before the PATCH.  When the refresher upserts to update ``diff_status``,
# the trigger's ``DO UPDATE SET <every column>`` rewrites every column from
# ``excluded`` — including ``is_open=True`` from the refresher's stale read.
# The PATCH is silently lost; the tab pops back open.
#
# This is a real bug on main today, independent of the SCU-168 ``is_deleted``
# race: the monotonic latch on ``is_deleted`` doesn't apply to ``is_open``
# (no monotonic ordering for arbitrary booleans).
#
# Fix: ``immediate=True`` on both writers serializes them via the SQLite
# writer slot.  The second writer's snapshot includes the first writer's
# commit, so its ``evolve`` sees an up-to-date workspace and the upsert
# preserves the first writer's field changes.
# ============================================================================


def _seed_workspace_with_open_state(
    service: SQLDataModelService,
    project_id: ProjectID,
    organization_reference: OrganizationReference,
    is_open: bool,
) -> WorkspaceID:
    workspace = Workspace(
        object_id=WorkspaceID(),
        project_id=project_id,
        organization_reference=organization_reference,
        description="seed",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        is_open=is_open,
    )
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_workspace(workspace)
    return workspace.object_id


def test_refresh_clobbers_is_open_patch_under_deferred(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Documents the lost-update bug under default DEFERRED transactions.

    Forces the racy interleaving:
      1. Refresher reads workspace (in-memory copy has is_open=True).
      2. PATCH commits is_open=False.
      3. Refresher upserts diff_status.  Its full-object upsert carries
         is_open=True from step 1 and the trigger's DO UPDATE SET writes
         every column, clobbering the PATCH.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace_with_open_state(service, project.object_id, organization_reference, is_open=True)

    refresher_read = threading.Event()
    patch_committed = threading.Event()

    def refresher() -> None:
        with service.open_transaction(RequestID()) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None
            assert workspace.is_open is True
            refresher_read.set()
            patch_committed.wait(timeout=5)
            # Upsert with the in-memory copy (still says is_open=True),
            # changing only diff_status.  The full-object upsert rewrites
            # all columns, so is_open=True overwrites the PATCH's False.
            transaction.upsert_workspace(workspace.evolve(workspace.ref().diff_status, DiffStatus.READY))

    def patcher() -> None:
        refresher_read.wait(timeout=2)
        with service.open_transaction(RequestID()) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None
            transaction.upsert_workspace(workspace.evolve(workspace.ref().is_open, False))
        patch_committed.set()

    refresher_thread = threading.Thread(target=refresher)
    patcher_thread = threading.Thread(target=patcher)
    refresher_thread.start()
    patcher_thread.start()
    refresher_thread.join(timeout=10)
    patcher_thread.join(timeout=10)
    assert not refresher_thread.is_alive()
    assert not patcher_thread.is_alive()

    with service.open_transaction(RequestID()) as transaction:
        final = transaction.get_workspace(workspace_id)
        assert final is not None
        # Documented bug: PATCH was clobbered by the refresher's stale upsert.
        assert final.is_open is True, "Expected the documented lost-update bug under DEFERRED"
        # Refresher's intended write did land:
        assert final.diff_status == DiffStatus.READY


def test_refresh_does_not_clobber_is_open_patch_under_immediate(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Same scenario but with ``immediate=True`` on both writers — the bug
    above does not occur.

    Under IMMEDIATE, the writer slot serializes the two transactions, so
    whichever one runs second takes a fresh snapshot that includes the first
    one's commit.  Its ``evolve`` then preserves the first writer's field
    change, and the full-object upsert no longer clobbers.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace_with_open_state(service, project.object_id, organization_reference, is_open=True)

    refresher_holds_writer = threading.Event()

    def refresher() -> None:
        # IMMEDIATE: acquires writer slot at BEGIN, snapshot is fresh.
        with service.open_transaction(RequestID(), immediate=True) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None
            refresher_holds_writer.set()
            # Hold the writer slot briefly so the patcher attempts BEGIN
            # IMMEDIATE while we hold the slot — proving serialization.
            time.sleep(0.3)
            transaction.upsert_workspace(workspace.evolve(workspace.ref().diff_status, DiffStatus.READY))

    def patcher() -> None:
        refresher_holds_writer.wait(timeout=2)
        # This BEGIN IMMEDIATE blocks until the refresher commits.
        with service.open_transaction(RequestID(), immediate=True) as transaction:
            # By the time we get here, the refresher has committed.
            # Our snapshot reflects diff_status=READY.
            workspace = transaction.get_workspace(workspace_id)
            assert workspace is not None
            assert workspace.diff_status == DiffStatus.READY, "Patcher's snapshot should reflect refresher's commit"
            # Evolve from the fresh read — preserves diff_status=READY.
            transaction.upsert_workspace(workspace.evolve(workspace.ref().is_open, False))

    refresher_thread = threading.Thread(target=refresher)
    patcher_thread = threading.Thread(target=patcher)
    refresher_thread.start()
    patcher_thread.start()
    refresher_thread.join(timeout=10)
    patcher_thread.join(timeout=10)
    assert not refresher_thread.is_alive()
    assert not patcher_thread.is_alive()

    with service.open_transaction(RequestID()) as transaction:
        final = transaction.get_workspace(workspace_id)
        assert final is not None
        # Both writes landed correctly:
        assert final.is_open is False, "PATCH preserved under IMMEDIATE"
        assert final.diff_status == DiffStatus.READY, "Refresher's diff_status preserved"


# ============================================================================
# SCU-474 — ``update_project_fields`` targeted-column updates.
#
# Unlike ``upsert_project``, ``update_project_fields`` only writes the named
# columns to ``project_latest``.  Unnamed columns are never mentioned in the
# SET clause, so two concurrent writers naming disjoint fields cannot
# clobber each other via full-object carry-through.
#
# The design:
#   1. ``UPDATE project_latest SET <named> WHERE object_id=? RETURNING *``
#   2. INSERT snapshot row from the returned post-update values (audit).
#   3. Append ``("UPDATE", project)`` to ``_updated_models`` for observer.
# ============================================================================


def test_update_project_fields_writes_only_named_columns(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, _, _, project = test_db_service_with_user_organization_and_project

    # Seed non-default values on fields we don't intend to touch.
    with service.open_transaction(RequestID()) as transaction:
        seeded = project.evolve(project.ref().default_system_prompt, "SEED_PROMPT")
        seeded = seeded.evolve(seeded.ref().workspace_setup_command, "SEED_SETUP")
        transaction.upsert_project(seeded)

    # Targeted update of ONE field.
    with service.open_transaction(RequestID()) as transaction:
        updated = transaction.update_project_fields(project.object_id, name="RENAMED")
        assert updated is not None
        assert updated.name == "RENAMED"
        assert updated.default_system_prompt == "SEED_PROMPT", "unnamed field clobbered"
        assert updated.workspace_setup_command == "SEED_SETUP", "unnamed field clobbered"

    # Re-read from DB to confirm.
    with service.open_transaction(RequestID()) as transaction:
        after = transaction.get_project(project.object_id)
        assert after is not None
        assert after.name == "RENAMED"
        assert after.default_system_prompt == "SEED_PROMPT"
        assert after.workspace_setup_command == "SEED_SETUP"


def test_update_project_fields_returns_none_for_missing_row(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, _, _, _ = test_db_service_with_user_organization_and_project
    nonexistent = ProjectID()
    with service.open_transaction(RequestID()) as transaction:
        result = transaction.update_project_fields(nonexistent, name="whatever")
        assert result is None


def test_update_project_fields_rejects_bad_inputs(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, _, _, project = test_db_service_with_user_organization_and_project

    # The TypedDict + Unpack signature gives static validation of kwargs —
    # type checkers reject unknown names and wrong types at the call site.
    # These runtime tests exercise the defense-in-depth belt inside
    # ``_update_model_fields`` for callers that might bypass static typing
    # (e.g. dynamic dict unpacking from untyped sources).  We drive the
    # internal helper directly so no pyre-ignore is needed.
    with service.open_transaction(RequestID()) as transaction:
        assert isinstance(transaction, SQLTransaction)
        with pytest.raises(ValueError, match="at least one field"):
            transaction.update_project_fields(project.object_id)

        def _exercise(bad_fields: dict[str, Any]) -> None:
            transaction._update_model_fields(
                model_cls=Project,
                snapshot_table=PROJECT_TABLE,
                latest_table=PROJECT_LATEST_TABLE,
                object_id=project.object_id,
                fields=bad_fields,
            )

        with pytest.raises(ValueError, match="Unknown"):
            _exercise({"not_a_real_field": "x"})

        with pytest.raises(ValueError, match="managed"):
            _exercise({"object_id": str(ProjectID())})

        with pytest.raises(ValueError, match="managed"):
            _exercise({"is_deleted": True})


def test_update_project_fields_emits_single_observer_notification(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project

    mock_queue: MagicMock = MagicMock()
    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        # Reset after the initial-state push
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            updated = transaction.update_project_fields(project.object_id, name="OBSERVED")
            assert updated is not None and updated.name == "OBSERVED"

        # Exactly one CompletedTransaction pushed, carrying the updated project.
        assert mock_queue.put.call_count == 1
        completed_transaction = mock_queue.put.call_args[0][0]
        assert len(completed_transaction.updated_models) == 1
        observed_project = completed_transaction.updated_models[0]
        assert isinstance(observed_project, Project)
        assert observed_project.object_id == project.object_id
        assert observed_project.name == "OBSERVED"


def test_update_project_fields_writes_exactly_one_snapshot_row(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Audit-log invariant: one targeted update = one new snapshot row.

    Even though the ``<table>_before_insert`` trigger fires on our snapshot
    INSERT and does a redundant ``ON CONFLICT DO UPDATE`` on ``_latest``,
    it does NOT insert an extra snapshot row.
    """
    service, _, _, project = test_db_service_with_user_organization_and_project

    with service.open_transaction(RequestID()) as transaction:
        before_rows = transaction.connection.execute(
            text("SELECT COUNT(*) FROM project WHERE object_id = :oid"), {"oid": str(project.object_id)}
        ).scalar()

    with service.open_transaction(RequestID()) as transaction:
        transaction.update_project_fields(project.object_id, name="SNAPSHOTTED")

    with service.open_transaction(RequestID()) as transaction:
        after_rows = transaction.connection.execute(
            text("SELECT COUNT(*) FROM project WHERE object_id = :oid"), {"oid": str(project.object_id)}
        ).scalar()

    assert after_rows == before_rows + 1, (
        f"Expected exactly one new snapshot row; got delta={after_rows - before_rows}"
    )


def test_update_project_fields_disjoint_concurrent_writers_do_not_clobber(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Two writers update different columns on the same row.  Both writes
    must land — neither can be lost to the other's stale read.

    Under the full-object ``upsert_project`` this race is documented in
    MR 986's reproduction tests.  ``update_project_fields`` eliminates it:
    each writer's SET clause names only its own column, so their UPDATEs
    are row-level mergable.
    """
    service, _, _, project = test_db_service_with_user_organization_and_project

    writer_a_read = threading.Event()
    writer_b_read = threading.Event()

    def writer_a() -> None:
        with service.open_transaction(RequestID()) as transaction:
            # Confirm both writers have taken autocommit-style reads of the
            # baseline before either writes, so we actually exercise the
            # "stale data in caller's hand" scenario.
            _ = transaction.get_project(project.object_id)
            writer_a_read.set()
            writer_b_read.wait(timeout=5)
            transaction.update_project_fields(project.object_id, default_system_prompt="A_PROMPT")

    def writer_b() -> None:
        with service.open_transaction(RequestID()) as transaction:
            _ = transaction.get_project(project.object_id)
            writer_b_read.set()
            writer_a_read.wait(timeout=5)
            transaction.update_project_fields(project.object_id, workspace_setup_command="B_SETUP")

    thread_a = threading.Thread(target=writer_a)
    thread_b = threading.Thread(target=writer_b)
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()

    with service.open_transaction(RequestID()) as transaction:
        final = transaction.get_project(project.object_id)
        assert final is not None
        assert final.default_system_prompt == "A_PROMPT", "A's update was lost"
        assert final.workspace_setup_command == "B_SETUP", "B's update was lost"


def test_update_project_fields_stress_disjoint_concurrent_writers(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """High-volume disjoint-field stress: N threads hammer one column each.

    Scales the single-iteration disjoint-writer test: ``N`` writers, each
    owning exactly one column, each doing ``ITERATIONS`` targeted updates
    back-to-back.  A ``Barrier`` ensures all threads begin their write
    loops in overlapping wall time so the SQLite writer slot sees real
    contention — not a pre-serialized one-after-another run.

    Invariant: after join, every writer's FINAL iteration value must be
    present in its column.  No writes lost to disjoint-field clobbering.
    Under ``upsert_project`` this would fail: each transaction's stale
    read of the other columns carries through the trigger's
    ``DO UPDATE SET <every column>``.
    """
    service, _, _, project = test_db_service_with_user_organization_and_project

    iterations = 25
    field_names = (
        "name",
        "default_system_prompt",
        "workspace_setup_command",
        "user_git_repo_url",
    )
    barrier = threading.Barrier(len(field_names))
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def writer(field_name: str) -> None:
        try:
            barrier.wait(timeout=10)
            for i in range(iterations):
                with service.open_transaction(RequestID()) as transaction:
                    transaction.update_project_fields(project.object_id, **{field_name: f"{field_name}_iter_{i}"})
        except BaseException as e:
            with errors_lock:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(f,)) for f in field_names]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "writer thread hung"
    assert not errors, f"writer threads raised: {errors!r}"

    with service.open_transaction(RequestID()) as transaction:
        final = transaction.get_project(project.object_id)
        assert final is not None
        for field_name in field_names:
            expected = f"{field_name}_iter_{iterations - 1}"
            actual = getattr(final, field_name)
            assert actual == expected, (
                f"writer for {field_name!r} lost its last write: expected {expected!r}, got {actual!r}"
            )


def test_update_project_fields_and_upsert_immediate_mix_concurrently(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Mixed-API stress: targeted updates + IMMEDIATE full-row upserts.

    Thread A hammers ``update_project_fields(default_system_prompt=...)``.
    Thread B hammers ``upsert_project`` in ``immediate=True`` transactions
    with a fresh read-then-evolve of ``name`` — the MR 986 pattern for
    legacy sites that can't migrate to targeted updates yet.

    Both writers must converge to their own final values.  IMMEDIATE on
    B's branch guarantees its snapshot observes any prior A commits; A's
    targeted UPDATE never asserts values on B's column.  This is the
    invariant that lets the two APIs coexist in the codebase during
    migration (see ``notes.md`` §"Open question for review").
    """
    service, _, _, project = test_db_service_with_user_organization_and_project

    iterations = 25
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def update_fields_writer() -> None:
        try:
            barrier.wait(timeout=10)
            for i in range(iterations):
                with service.open_transaction(RequestID()) as transaction:
                    transaction.update_project_fields(project.object_id, default_system_prompt=f"A_iter_{i}")
        except BaseException as e:
            with errors_lock:
                errors.append(e)

    def upsert_writer() -> None:
        try:
            barrier.wait(timeout=10)
            for i in range(iterations):
                with service.open_transaction(RequestID(), immediate=True) as transaction:
                    fresh = transaction.get_project(project.object_id)
                    assert fresh is not None
                    transaction.upsert_project(fresh.model_copy(update={"name": f"B_iter_{i}"}))
        except BaseException as e:
            with errors_lock:
                errors.append(e)

    threads = [
        threading.Thread(target=update_fields_writer),
        threading.Thread(target=upsert_writer),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "writer thread hung"
    assert not errors, f"writer threads raised: {errors!r}"

    with service.open_transaction(RequestID()) as transaction:
        final = transaction.get_project(project.object_id)
        assert final is not None
        assert final.default_system_prompt == f"A_iter_{iterations - 1}", "targeted-update writer lost its final write"
        assert final.name == f"B_iter_{iterations - 1}", "IMMEDIATE upsert writer lost its final write"


def test_project_field_update_typeddict_matches_project_model() -> None:
    """Drift guard for :py:class:`ProjectFieldUpdate` vs :py:class:`Project`.

    Catches both:
    * field-presence drift (a new ``Project`` field silently not picked up
      by the TypedDict, or a removed field still listed);
    * type-annotation drift (a field's type changed in ``Project``, e.g.
      from ``str`` to ``str | None`` or to a different enum, without the
      TypedDict being updated).

    Fields that are intentionally excluded from the TypedDict are listed
    explicitly here — when someone adds a new ``Project`` field, they must
    either add it to ``ProjectFieldUpdate`` or add it to this exclusion
    set with a comment explaining why it's not field-updatable.
    """
    # Universal "never written via update_*_fields" set + per-model
    # exclusions. Keep these explicit: drift should force a deliberate
    # choice about whether to expose a new field for targeted updates.
    intentionally_excluded = _UPDATE_FIELDS_PROTECTED_COLUMNS | {
        # organization_reference is set at project creation; changing it
        # via a field-level update would effectively re-parent the project.
        "organization_reference",
    }

    expected_annotations: dict[str, Any] = {
        name: field.annotation for name, field in Project.model_fields.items() if name not in intentionally_excluded
    }
    actual_annotations: dict[str, Any] = dict(typing.get_type_hints(ProjectFieldUpdate))

    # Key-set match: any field added/removed on Project (vs the exclusion
    # list) must be mirrored in ProjectFieldUpdate.
    missing = set(expected_annotations) - set(actual_annotations)
    unexpected = set(actual_annotations) - set(expected_annotations)
    assert not missing and not unexpected, (
        f"ProjectFieldUpdate keys drifted from Project. missing_from_typeddict={sorted(missing)} unexpected_in_typeddict={sorted(unexpected)}. Add the missing fields, remove the unexpected ones, or add the field to ``intentionally_excluded`` in this test with a comment."
    )

    # Type-equality match: each field's annotation must be identical
    # between Project and ProjectFieldUpdate.
    mismatched = {
        name: (expected_annotations[name], actual_annotations[name])
        for name in expected_annotations
        if expected_annotations[name] != actual_annotations[name]
    }
    assert not mismatched, "ProjectFieldUpdate type annotations diverged from Project: " + ", ".join(
        f"{name}: Project has {exp!r}, TypedDict has {act!r}" for name, (exp, act) in mismatched.items()
    )


def _seed_workspace(
    service: SQLDataModelService,
    project_id: ProjectID,
    organization_reference: OrganizationReference,
) -> WorkspaceID:
    workspace = Workspace(
        object_id=WorkspaceID(),
        project_id=project_id,
        organization_reference=organization_reference,
        description="seed",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_workspace(workspace)
    return workspace.object_id


def test_update_workspace_fields_writes_only_named_columns(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    # Seed non-default values on fields we don't intend to touch.
    with service.open_transaction(RequestID()) as transaction:
        seeded = transaction.get_workspace(workspace_id)
        assert seeded is not None
        seeded = seeded.evolve(seeded.ref().description, "SEED_DESCRIPTION")
        seeded = seeded.evolve(seeded.ref().target_branch, "main")
        transaction.upsert_workspace(seeded)

    # Targeted update of ONE field.
    with service.open_transaction(RequestID()) as transaction:
        updated = transaction.update_workspace_fields(workspace_id, diff_status=DiffStatus.READY)
        assert updated is not None
        assert updated.diff_status == DiffStatus.READY
        assert updated.description == "SEED_DESCRIPTION", "unnamed field clobbered"
        assert updated.target_branch == "main", "unnamed field clobbered"

    # Re-read from DB to confirm.
    with service.open_transaction(RequestID()) as transaction:
        after = transaction.get_workspace(workspace_id)
        assert after is not None
        assert after.diff_status == DiffStatus.READY
        assert after.description == "SEED_DESCRIPTION"
        assert after.target_branch == "main"


def test_update_workspace_fields_returns_none_for_missing_row(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, _, _, _ = test_db_service_with_user_organization_and_project
    nonexistent = WorkspaceID()
    with service.open_transaction(RequestID()) as transaction:
        result = transaction.update_workspace_fields(nonexistent, description="whatever")
        assert result is None


def test_update_workspace_fields_returns_none_for_soft_deleted_row(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """A targeted update on a soft-deleted workspace must return ``None``
    and leave the row unchanged: the wrapper's ``is_deleted=False`` filter
    prevents writing other columns through a tombstone.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    # Soft-delete the workspace.
    with service.open_transaction(RequestID()) as transaction:
        ws = transaction.get_workspace(workspace_id)
        assert ws is not None
        transaction.upsert_workspace(ws.evolve(ws.ref().is_deleted, True))

    # Targeted update should refuse the tombstone and leave is_deleted=True.
    with service.open_transaction(RequestID()) as transaction:
        result = transaction.update_workspace_fields(workspace_id, diff_status=DiffStatus.READY)
        assert result is None

    with service.open_transaction(RequestID()) as transaction:
        after = transaction.get_workspace_include_deleted(workspace_id)
        assert after is not None
        assert after.is_deleted is True
        assert after.diff_status == DiffStatus.NONE, "tombstone column was written through"


def test_update_workspace_fields_rejects_bad_inputs(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    with service.open_transaction(RequestID()) as transaction:
        assert isinstance(transaction, SQLTransaction)
        with pytest.raises(ValueError, match="at least one field"):
            transaction.update_workspace_fields(workspace_id)

        def _exercise(bad_fields: dict[str, Any]) -> None:
            transaction._update_model_fields(
                model_cls=Workspace,
                snapshot_table=WORKSPACE_TABLE,
                latest_table=WORKSPACE_LATEST_TABLE,
                object_id=workspace_id,
                fields=bad_fields,
            )

        with pytest.raises(ValueError, match="Unknown"):
            _exercise({"not_a_real_field": "x"})

        with pytest.raises(ValueError, match="managed"):
            _exercise({"object_id": str(WorkspaceID())})

        with pytest.raises(ValueError, match="managed"):
            _exercise({"is_deleted": True})


def test_update_workspace_fields_emits_single_observer_notification(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    mock_queue: MagicMock = MagicMock()
    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            updated = transaction.update_workspace_fields(workspace_id, description="OBSERVED")
            assert updated is not None and updated.description == "OBSERVED"

        assert mock_queue.put.call_count == 1
        completed_transaction = mock_queue.put.call_args[0][0]
        assert len(completed_transaction.updated_models) == 1
        observed_workspace = completed_transaction.updated_models[0]
        assert isinstance(observed_workspace, Workspace)
        assert observed_workspace.object_id == workspace_id
        assert observed_workspace.description == "OBSERVED"


def test_update_workspace_fields_writes_exactly_one_snapshot_row(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """One targeted update = one new snapshot row, even though the
    BEFORE INSERT trigger re-fires on the snapshot.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    with service.open_transaction(RequestID()) as transaction:
        before_rows = transaction.connection.execute(
            text("SELECT COUNT(*) FROM workspace WHERE object_id = :oid"), {"oid": str(workspace_id)}
        ).scalar()

    with service.open_transaction(RequestID()) as transaction:
        transaction.update_workspace_fields(workspace_id, description="SNAPSHOTTED")

    with service.open_transaction(RequestID()) as transaction:
        after_rows = transaction.connection.execute(
            text("SELECT COUNT(*) FROM workspace WHERE object_id = :oid"), {"oid": str(workspace_id)}
        ).scalar()

    assert after_rows == before_rows + 1, (
        f"Expected exactly one new snapshot row; got delta={after_rows - before_rows}"
    )


def test_update_workspace_fields_disjoint_concurrent_writers_do_not_clobber(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
) -> None:
    """Two writers update different columns on the same workspace.  Both
    writes must land — each writer's SET clause names only its own column,
    so the UPDATEs are row-level mergable.
    """
    service, _, organization_reference, project = test_db_service_with_user_organization_and_project
    workspace_id = _seed_workspace(service, project.object_id, organization_reference)

    writer_a_read = threading.Event()
    writer_b_read = threading.Event()

    def writer_a() -> None:
        with service.open_transaction(RequestID()) as transaction:
            _ = transaction.get_workspace(workspace_id)
            writer_a_read.set()
            writer_b_read.wait(timeout=5)
            transaction.update_workspace_fields(workspace_id, is_open=False)

    def writer_b() -> None:
        with service.open_transaction(RequestID()) as transaction:
            _ = transaction.get_workspace(workspace_id)
            writer_b_read.set()
            writer_a_read.wait(timeout=5)
            transaction.update_workspace_fields(workspace_id, diff_status=DiffStatus.READY)

    thread_a = threading.Thread(target=writer_a)
    thread_b = threading.Thread(target=writer_b)
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()

    with service.open_transaction(RequestID()) as transaction:
        final = transaction.get_workspace(workspace_id)
        assert final is not None
        assert final.is_open is False, "A's update was lost"
        assert final.diff_status == DiffStatus.READY, "B's update was lost"


def test_workspace_field_update_typeddict_matches_workspace_model() -> None:
    """Drift guard for :py:class:`WorkspaceFieldUpdate` vs :py:class:`Workspace`."""
    intentionally_excluded = _UPDATE_FIELDS_PROTECTED_COLUMNS | WORKSPACE_CREATION_ONLY_FIELDS

    expected_annotations: dict[str, Any] = {
        name: field.annotation for name, field in Workspace.model_fields.items() if name not in intentionally_excluded
    }
    actual_annotations: dict[str, Any] = dict(typing.get_type_hints(WorkspaceFieldUpdate))

    missing = set(expected_annotations) - set(actual_annotations)
    unexpected = set(actual_annotations) - set(expected_annotations)
    assert not missing and not unexpected, (
        f"WorkspaceFieldUpdate keys drifted from Workspace. missing_from_typeddict={sorted(missing)} unexpected_in_typeddict={sorted(unexpected)}. Add the missing fields, remove the unexpected ones, or add the field to ``intentionally_excluded`` in this test with a comment."
    )

    mismatched = {
        name: (expected_annotations[name], actual_annotations[name])
        for name in expected_annotations
        if expected_annotations[name] != actual_annotations[name]
    }
    assert not mismatched, "WorkspaceFieldUpdate type annotations diverged from Workspace: " + ", ".join(
        f"{name}: Workspace has {exp!r}, TypedDict has {act!r}" for name, (exp, act) in mismatched.items()
    )
