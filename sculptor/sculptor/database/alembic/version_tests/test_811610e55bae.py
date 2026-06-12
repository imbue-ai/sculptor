import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"


class TestTasksRequireWorkspace(MigrationTestFixture):
    """Test fixture for the migration that creates workspace tables and assigns workspaces to tasks."""

    @property
    def revision(self) -> str:
        return "811610e55bae"

    @property
    def down_revision(self) -> str:
        return "9bb41574855c"

    def seed(self, connection: sa.engine.Connection) -> None:
        # Insert a project
        connection.execute(
            sa.text("""
                INSERT INTO project (
                    snapshot_id, created_at, object_id, organization_reference,
                    name, user_git_repo_url, is_loggable, is_path_accessible,
                    is_deleted, default_system_prompt
                ) VALUES (
                    'snap-proj-1', '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', NULL, 1, 1, 0, NULL
                )
            """),
            {"project_id": PROJECT_ID},
        )
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

        # Insert a task without workspace_id in current_state
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
        # Check workspace tables exist
        tables = {row[0] for row in connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "workspace" in tables, "workspace table not found"
        assert "workspace_latest" in tables, "workspace_latest table not found"

        # Check a workspace was created
        workspace_rows = connection.execute(sa.text("SELECT COUNT(*) FROM workspace")).fetchone()
        assert workspace_rows is not None
        assert workspace_rows[0] >= 1, "No workspace rows were created"

        # Check task_latest current_state now contains workspace_id
        result = connection.execute(
            sa.text("""
                SELECT json_extract(current_state, '$.workspace_id')
                FROM task_latest
                WHERE object_id = :task_id
            """),
            {"task_id": TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Task not found in task_latest"
        assert row[0] is not None, "workspace_id not added to task current_state"
