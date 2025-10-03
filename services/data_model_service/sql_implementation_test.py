import sqlite3
import threading
import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches_test import expect_exact_logged_errors
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from sculptor.agents.hello_agent.agent import HelloAgentConfig
from sculptor.config.settings import SculptorSettings
from sculptor.database.alembic.json_migrations import get_json_schemas_of_all_nested_models
from sculptor.database.alembic.json_migrations import get_potentially_breaking_changes
from sculptor.database.alembic.utils import get_frozen_database_model_nested_json_schemas
from sculptor.database.automanaged import AUTOMANAGED_MODEL_CLASSES
from sculptor.database.core import METADATA
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import ProductLoggingPermissionLevel
from sculptor.database.models import Project
from sculptor.database.models import SavedAgentMessage
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import UserSettings
from sculptor.interfaces.environments.v1.base import LocalImageConfig
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import UserSettingsID
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService


@pytest.fixture
def test_db_service(test_settings: SculptorSettings) -> Generator[SQLDataModelService, None, None]:
    service = SQLDataModelService.build_from_settings(test_settings)
    service.start()
    try:
        yield service
    finally:
        service.stop()


@pytest.fixture
def test_db_service_with_user_organization_and_project(
    test_db_service: SQLDataModelService,
) -> tuple[SQLDataModelService, UserReference, OrganizationReference, Project]:
    user_reference = UserReference("authentik-dummy-id")
    organization_reference = OrganizationReference("authentik-dummy-organization-id")
    with test_db_service.open_transaction(RequestID()) as transaction:
        project = Project(object_id=ProjectID(), name="Example Project", organization_reference=organization_reference)
        transaction.upsert_project(project)
        user_settings = transaction.get_or_create_user_settings(user_reference)
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
        input_data=AgentTaskInputsV1(
            agent_config=HelloAgentConfig(),
            image_config=LocalImageConfig(code_directory=code_directory),
            available_secrets=None,
            git_hash="HEAD",
            initial_branch="main",
            is_git_state_clean=False,
        ),
        organization_reference=organization_reference,
        user_reference=user_reference,
        parent_task_id=None,
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
        assert maybe_task == None, "Expected no task to exist before insertion."
    with service.open_transaction(RequestID()) as transaction:
        inserted_task = transaction.upsert_task(task)
        for field in Task.model_fields:
            assert getattr(inserted_task, field) == getattr(task, field), f"Expected {field} to be the same."
    with service.open_transaction(RequestID()) as transaction:
        task = transaction.get_task(task_id)
        assert task == inserted_task, "Expected the retrieved task to match the inserted task."


def test_foreign_constraints_are_being_enforced(test_db_service: SQLDataModelService, tmp_path: Path) -> None:
    message_id = AgentMessageID()
    saved_agent_message = SavedAgentMessage.build(
        message=ChatInputUserMessage(message_id=message_id, text="Hello, world!", model_name=LLMModel.CLAUDE_4_SONNET),
        task_id=TaskID(),
    )
    with pytest.raises(IntegrityError):
        with test_db_service.open_transaction(RequestID()) as transaction:
            maybe_task = transaction.insert_message(saved_agent_message)


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
# OBSERVER AND TELEMETRY BEHAVIOR TESTS
# These tests verify the current behavior by mocking the actual outputs:
# - Observer notifications via queue.put() calls
# - Telemetry emissions via emit_posthog_event() calls
# This ensures refactoring doesn't break existing functionality.
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


def test_observer_notification_user_settings_upsert(test_db_service: SQLDataModelService) -> None:
    """Test that User upsert operations trigger observer notifications."""
    user_reference = UserReference("test-user-id")
    organization_reference = OrganizationReference("test-org-id")
    with test_db_service.open_transaction(RequestID()) as transaction:
        user_settings = transaction.get_or_create_user_settings(user_reference)

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with test_db_service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        # Update the user settings to trigger a notification
        user_settings_updated = user_settings.model_copy(
            update={"allowed_product_logging": ProductLoggingPermissionLevel.OPEN_SOURCE}
        )
        with test_db_service.open_transaction(RequestID()) as transaction:
            transaction.upsert_user_settings(user_settings_updated)

        # Verify that the observer was called with a CompletedTransaction containing the user
        mock_queue.put.assert_called_once()
        completed_transaction = mock_queue.put.call_args[0][0]

        assert len(completed_transaction.updated_models) == 1
        assert completed_transaction.updated_models[0] == user_settings_updated


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


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_project_upsert(mock_emit_posthog_event, test_db_service: SQLDataModelService) -> None:
    """Test that Project upsert operations emit telemetry to PostHog."""
    organization_reference = OrganizationReference("test-org-id")
    # Reset the mock to only capture the project telemetry
    mock_emit_posthog_event.reset_mock()

    project = Project(object_id=ProjectID(), name="Test Project", organization_reference=organization_reference)

    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_project(project)

    # Verify that emit_posthog_event was called
    mock_emit_posthog_event.assert_called_once()

    # Verify the event data structure
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.table_name == "project"
    assert call_args.payload.operation == "INSERT"
    assert call_args.payload.model_data == project.model_dump()


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_user_settings_upsert(
    mock_emit_posthog_event, test_db_service: SQLDataModelService
) -> None:
    """Test that User upsert operations emit telemetry to PostHog."""
    user_settings = UserSettings(object_id=UserSettingsID(), user_reference=UserReference("test-user-id"))

    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_user_settings(user_settings)

    # Verify that emit_posthog_event was called
    mock_emit_posthog_event.assert_called_once()

    # Verify the event data structure
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.table_name == "user_settings"
    assert call_args.payload.operation == "INSERT"
    assert call_args.payload.model_data == user_settings.model_dump()


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_task_upsert(
    mock_emit_posthog_event,
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that Task upsert operations emit telemetry to PostHog."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_task(task)

    # Verify that emit_posthog_event was called
    mock_emit_posthog_event.assert_called_once()

    # Verify the event data structure
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.table_name == "task"
    assert call_args.payload.operation == "INSERT"
    assert call_args.payload.model_data == task.model_dump()


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_notification_insert(
    mock_emit_posthog_event,
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that Notification insert operations emit telemetry to PostHog."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    # We need to isolate the notification telemetry from the task telemetry
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_task(task)

    # Reset the mock to only capture the notification telemetry
    mock_emit_posthog_event.reset_mock()

    with service.open_transaction(RequestID()) as transaction:
        notification = Notification(
            object_id=NotificationID(),
            user_reference=user_reference,
            task_id=task.object_id,
            message="Test notification",
        )
        transaction.insert_notification(notification)

    # Verify that emit_posthog_event was called for the notification
    mock_emit_posthog_event.assert_called_once()

    # Verify the event data structure
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.table_name == "notification"
    assert call_args.payload.operation == "INSERT"
    assert call_args.payload.model_data == notification.model_dump()


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_saved_agent_message_insert(
    mock_emit_posthog_event,
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that SavedAgentMessage insert operations emit telemetry to PostHog."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)

    # Setup task first
    with service.open_transaction(RequestID()) as transaction:
        transaction.upsert_task(task)

    # Reset the mock to only capture the message telemetry
    mock_emit_posthog_event.reset_mock()

    with service.open_transaction(RequestID()) as transaction:
        message_id = AgentMessageID()
        message = SavedAgentMessage.build(
            message=ChatInputUserMessage(
                message_id=message_id, text="Test message", model_name=LLMModel.CLAUDE_4_SONNET
            ),
            task_id=task.object_id,
        )
        transaction.insert_message(message)

    # Verify that emit_posthog_event was called for the message
    mock_emit_posthog_event.assert_called_once()

    # Verify the event data structure
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.table_name == "saved_agent_message"
    assert call_args.payload.operation == "INSERT"
    assert call_args.payload.model_data == message.model_dump()


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_update_vs_insert_operations(
    mock_emit_posthog_event, test_db_service: SQLDataModelService
) -> None:
    """Test that telemetry correctly distinguishes between INSERT and UPDATE operations."""
    user_settings = UserSettings(object_id=UserSettingsID(), user_reference=UserReference("test-user-id"))

    # First upsert - should emit INSERT telemetry
    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_user_settings(user_settings)

    mock_emit_posthog_event.assert_called_once()
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.operation == "INSERT"
    assert call_args.payload.model_data == user_settings.model_dump()

    # Reset for next test
    mock_emit_posthog_event.reset_mock()

    # Second upsert with same data - should NOT emit telemetry (no change)
    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_user_settings(user_settings)

    mock_emit_posthog_event.assert_not_called()

    # Third upsert with changed data - should emit UPDATE telemetry
    user_settings_updated = user_settings.model_copy(
        update={"allowed_product_logging": ProductLoggingPermissionLevel.OPEN_SOURCE}
    )
    with test_db_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_user_settings(user_settings_updated)

    mock_emit_posthog_event.assert_called_once()
    call_args = mock_emit_posthog_event.call_args[0][0]
    assert call_args.payload.operation == "UPDATE"
    assert call_args.payload.model_data == user_settings_updated.model_dump()


def test_observer_notification_mixed_operations_behavior(
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that observers only receive notifications for models that should be observed."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    with service.open_transaction(RequestID()) as transaction:
        user_settings = transaction.get_user_settings(user_reference)
    assert user_settings is not None

    # Create a mock queue to act as an observer
    mock_queue = MagicMock()

    with service.observe_user_changes(user_reference, organization_reference, mock_queue):
        mock_queue.reset_mock()

        with service.open_transaction(RequestID()) as transaction:
            # Mix of observed and non-observed operations
            # Note: user and project already exist, so we need to modify them to get observer notifications
            project_updated = project.model_copy(update={"name": "Updated Project"})
            transaction.upsert_project(project_updated)  # Should be observed (UPDATE)

            user_settings = user_settings.evolve(
                user_settings.ref().allowed_product_logging, ProductLoggingPermissionLevel.OPEN_SOURCE
            )
            transaction.upsert_user_settings(user_settings)

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
        assert len(completed_transaction.updated_models) == 3  # user, project, notification
        model_types = [type(model).__name__ for model in completed_transaction.updated_models]
        assert "UserSettings" in model_types
        assert "Project" in model_types
        assert "Notification" in model_types
        assert "Task" not in model_types  # Task should NOT be included


@patch("sculptor.services.data_model_service.sql_implementation.emit_posthog_event")
def test_telemetry_emission_mixed_operations_behavior(
    mock_emit_posthog_event,
    test_db_service_with_user_organization_and_project: tuple[
        SQLDataModelService, UserReference, OrganizationReference, Project
    ],
    tmp_path: Path,
) -> None:
    """Test that telemetry is emitted for all models that should be tracked."""
    service, user_reference, organization_reference, project = test_db_service_with_user_organization_and_project
    task = get_simple_agent_task(tmp_path, user_reference, organization_reference, project)
    with service.open_transaction(RequestID()) as transaction:
        user_settings = transaction.get_user_settings(user_reference)
    assert user_settings is not None

    # Reset the mock to only capture our test operations (not the fixture setup)
    mock_emit_posthog_event.reset_mock()

    with service.open_transaction(RequestID()) as transaction:
        # Mix of telemetry-tracked and non-tracked operations
        # Note: user settings and project already exist, so no telemetry will be emitted for them
        # unless we modify them

        project_updated = project.model_copy(update={"name": "Updated Project"})
        transaction.upsert_project(project_updated)  # Should emit telemetry (UPDATE)

        user_settings = user_settings.evolve(
            user_settings.ref().allowed_product_logging, ProductLoggingPermissionLevel.OPEN_SOURCE
        )
        transaction.upsert_user_settings(user_settings)

        transaction.upsert_task(task)  # Should emit telemetry (INSERT)

        notification = Notification(
            object_id=NotificationID(),
            user_reference=user_reference,
            task_id=task.object_id,
            message="Test notification",
        )
        transaction.insert_notification(notification)  # Should emit telemetry (INSERT)

        # Organization operations should NOT emit telemetry (but we're not doing any here)

    # Verify that emit_posthog_event was called 4 times (user, project, task, notification)
    assert mock_emit_posthog_event.call_count == 4

    # Verify all the expected models were tracked
    emitted_table_names = [call[0][0].payload.table_name for call in mock_emit_posthog_event.call_args_list]
    assert "user_settings" in emitted_table_names
    assert "project" in emitted_table_names
    assert "task" in emitted_table_names
    assert "notification" in emitted_table_names


def _slow_transaction_thread(service: SQLDataModelService, user_reference) -> None:
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
