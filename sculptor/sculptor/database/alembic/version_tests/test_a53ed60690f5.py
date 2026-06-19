import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"


class TestDropParentTaskId(MigrationTestFixture):
    """Test fixture for the migration that drops the parent_task_id column from task tables."""

    @property
    def revision(self) -> str:
        return "a53ed60690f5"

    @property
    def down_revision(self) -> str:
        return "5dd608c57dc6"

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

        # Insert a task with parent_task_id = NULL
        input_data = json.dumps(
            {
                "object_type": "AgentTaskInputsV2",
                "agent_config": {"object_type": "HelloAgentConfig"},
                "git_hash": "abc123",
                "system_prompt": None,
            }
        )
        current_state = json.dumps(
            {
                "object_type": "AgentTaskStateV2",
                "last_processed_message_id": None,
                "title": "Test Task",
                "mode": "IN_PLACE",
                "environment_id": "env-1",
                "source_branch": "main",
                "workspace_id": "ws-1",
            }
        )
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, parent_task_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_archived, is_archiving, is_deleted, is_deleting
                ) VALUES (
                    'snap-task-1', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, NULL, :input_data,
                    NULL, :current_state, 'PENDING', NULL,
                    0, 0, 0, 0
                )
            """),
            {
                "task_id": TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": current_state,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO task_latest (
                    created_at, object_id, organization_reference,
                    user_reference, project_id, parent_task_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_archived, is_archiving, is_deleted, is_deleting
                ) VALUES (
                    '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, NULL, :input_data,
                    NULL, :current_state, 'PENDING', NULL,
                    0, 0, 0, 0
                )
            """),
            {
                "task_id": TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": current_state,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        task_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(task)"))}
        assert "parent_task_id" not in task_columns, "parent_task_id still in task table"

        task_latest_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(task_latest)"))}
        assert "parent_task_id" not in task_latest_columns, "parent_task_id still in task_latest table"

        result = connection.execute(
            sa.text("SELECT object_id, outcome FROM task_latest WHERE object_id = :task_id"),
            {"task_id": TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Task data not preserved after migration"
        assert row[0] == TASK_ID
        assert row[1] == "PENDING"
