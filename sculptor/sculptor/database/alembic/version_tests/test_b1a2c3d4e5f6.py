import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
ARCHIVED_TASK_ID = "task-test-archived"
QUEUED_TASK_ID = "task-test-queued"


class TestConvertArchivedOutcomeToDeleted(MigrationTestFixture):
    """Test fixture for the migration that converts ARCHIVED outcomes to DELETED."""

    @property
    def revision(self) -> str:
        return "b1a2c3d4e5f6"

    @property
    def down_revision(self) -> str:
        return "0fb6dc48c8ef"

    def seed(self, connection: sa.engine.Connection) -> None:
        # Insert a project
        connection.execute(
            sa.text("""
                INSERT INTO project_latest (
                    created_at, object_id, organization_reference,
                    name, user_git_repo_url, is_loggable, is_path_accessible,
                    is_deleted, default_system_prompt
                ) VALUES (
                    '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', NULL, 1, 1, 0, NULL
                )
            """),
            {"project_id": PROJECT_ID},
        )

        input_data = json.dumps(
            {
                "object_type": "AgentTaskInputsV2",
                "agent_config": {"object_type": "HelloAgentConfig"},
                "git_hash": "abc123",
                "system_prompt": None,
            }
        )

        # Insert a task with outcome='ARCHIVED' (left over from broken migration)
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    'snap-archived', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'ARCHIVED', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": ARCHIVED_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO task_latest (
                    created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'ARCHIVED', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": ARCHIVED_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )

        # Insert a normal QUEUED task to verify it's not affected
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    'snap-queued', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'QUEUED', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": QUEUED_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO task_latest (
                    created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'QUEUED', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": QUEUED_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # ARCHIVED outcome should be converted to DELETED in task table
        result = connection.execute(
            sa.text("SELECT outcome FROM task WHERE object_id = :task_id"),
            {"task_id": ARCHIVED_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Archived task not found after migration"
        assert row[0] == "DELETED", f"Expected outcome DELETED, got {row[0]}"

        # ARCHIVED outcome should be converted to DELETED in task_latest table
        result = connection.execute(
            sa.text("SELECT outcome FROM task_latest WHERE object_id = :task_id"),
            {"task_id": ARCHIVED_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Archived task not found in task_latest after migration"
        assert row[0] == "DELETED", f"Expected outcome DELETED in task_latest, got {row[0]}"

        # QUEUED task should be unaffected
        result = connection.execute(
            sa.text("SELECT outcome FROM task WHERE object_id = :task_id"),
            {"task_id": QUEUED_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Queued task not found after migration"
        assert row[0] == "QUEUED", f"Expected outcome QUEUED, got {row[0]}"
