import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"


class TestAddLastReadAtToTask(MigrationTestFixture):
    """Test fixture for the migration that adds last_read_at to task tables."""

    @property
    def revision(self) -> str:
        return "2755d9e9f872"

    @property
    def down_revision(self) -> str:
        return "8522ec5edc2a"

    def seed(self, connection: sa.engine.Connection) -> None:
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
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_archived, is_archiving, is_deleted, is_deleting
                ) VALUES (
                    'snap-task-1', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'PENDING', NULL,
                    0, 0, 0, 0
                )
            """),
            {
                "task_id": TASK_ID,
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
                    is_archived, is_archiving, is_deleted, is_deleting
                ) VALUES (
                    '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'PENDING', NULL,
                    0, 0, 0, 0
                )
            """),
            {
                "task_id": TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        task_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(task)"))}
        assert "last_read_at" in task_columns, "last_read_at column not found in task"

        task_latest_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(task_latest)"))}
        assert "last_read_at" in task_latest_columns, "last_read_at column not found in task_latest"

        # Check existing task has last_read_at = NULL (nullable column, no default)
        result = connection.execute(
            sa.text("SELECT last_read_at FROM task WHERE object_id = :task_id"),
            {"task_id": TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Task not found after migration"
        assert row[0] is None, f"Expected last_read_at to be NULL, got {row[0]}"
