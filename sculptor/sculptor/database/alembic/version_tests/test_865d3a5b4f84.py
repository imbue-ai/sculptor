import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"


class TestDropArchiveColumnsFromTask(MigrationTestFixture):
    """Test fixture for the migration that drops is_archived and is_archiving from task tables."""

    @property
    def revision(self) -> str:
        return "865d3a5b4f84"

    @property
    def down_revision(self) -> str:
        return "2755d9e9f872"

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

        # Insert a task with is_archived=1 to test data preservation
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
                    is_archived, is_archiving, is_deleted, is_deleting,
                    last_read_at
                ) VALUES (
                    'snap-task-1', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'QUEUED', NULL,
                    1, 0, 0, 0,
                    NULL
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
                    is_archived, is_archiving, is_deleted, is_deleting,
                    last_read_at
                ) VALUES (
                    '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'QUEUED', NULL,
                    1, 0, 0, 0,
                    NULL
                )
            """),
            {
                "task_id": TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Check is_archived and is_archiving columns are removed from task
        task_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(task)"))}
        assert "is_archived" not in task_columns, "is_archived column still exists in task"
        assert "is_archiving" not in task_columns, "is_archiving column still exists in task"

        # Check is_archived and is_archiving columns are removed from task_latest
        task_latest_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(task_latest)"))}
        assert "is_archived" not in task_latest_columns, "is_archived column still exists in task_latest"
        assert "is_archiving" not in task_latest_columns, "is_archiving column still exists in task_latest"

        # Check the existing task's other data is preserved
        result = connection.execute(
            sa.text("SELECT object_id, outcome FROM task WHERE object_id = :task_id"),
            {"task_id": TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Task not found after migration"
        assert row[1] == "QUEUED", f"Expected outcome QUEUED, got {row[1]}"
