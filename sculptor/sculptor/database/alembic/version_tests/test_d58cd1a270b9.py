import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
DELETED_TASK_ID = "task-test-deleted"
DELETED_WITH_WS_TASK_ID = "task-test-deleted-with-ws"
ACTIVE_TASK_ID = "task-test-active"


class TestHardDeleteTasksMissingWorkspaceId(MigrationTestFixture):
    """Test that deleted AgentTaskStateV2 tasks without workspace_id are hard-deleted."""

    @property
    def revision(self) -> str:
        return "d58cd1a270b9"

    @property
    def down_revision(self) -> str:
        return "593675cc4b70"

    def seed(self, connection: sa.engine.Connection) -> None:
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

        input_data = json.dumps(
            {
                "object_type": "AgentTaskInputsV2",
                "agent_config": {"object_type": "HelloAgentConfig"},
                "git_hash": "abc123",
                "system_prompt": None,
            }
        )

        # A deleted task WITHOUT workspace_id (the bug scenario)
        deleted_state = json.dumps(
            {
                "object_type": "AgentTaskStateV2",
                "last_processed_message_id": None,
                "title": "Deleted Task",
                "mode": "IN_PLACE",
                "environment_id": "env-1",
                "source_branch": "main",
            }
        )
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    'snap-deleted', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, :current_state, 'DELETED', NULL,
                    1, 0, NULL
                )
            """),
            {
                "task_id": DELETED_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": deleted_state,
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
                    NULL, :current_state, 'DELETED', NULL,
                    1, 0, NULL
                )
            """),
            {
                "task_id": DELETED_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": deleted_state,
            },
        )

        # A deleted task WITH workspace_id (should NOT be hard-deleted)
        deleted_with_ws_state = json.dumps(
            {
                "object_type": "AgentTaskStateV2",
                "last_processed_message_id": None,
                "title": "Deleted Task With Workspace",
                "workspace_id": "ws-deleted-1",
            }
        )
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    'snap-deleted-ws', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, :current_state, 'DELETED', NULL,
                    1, 0, NULL
                )
            """),
            {
                "task_id": DELETED_WITH_WS_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": deleted_with_ws_state,
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
                    NULL, :current_state, 'DELETED', NULL,
                    1, 0, NULL
                )
            """),
            {
                "task_id": DELETED_WITH_WS_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": deleted_with_ws_state,
            },
        )

        # An active task that already has workspace_id (should be unaffected)
        active_state = json.dumps(
            {
                "object_type": "AgentTaskStateV2",
                "last_processed_message_id": None,
                "title": "Active Task",
                "workspace_id": "ws-existing-1",
            }
        )
        connection.execute(
            sa.text("""
                INSERT INTO task (
                    snapshot_id, created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    'snap-active', '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, :current_state, 'QUEUED', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": ACTIVE_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": active_state,
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
                    NULL, :current_state, 'QUEUED', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": ACTIVE_TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
                "current_state": active_state,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Deleted task should be hard-deleted from both tables
        result = connection.execute(
            sa.text("SELECT COUNT(*) FROM task_latest WHERE object_id = :task_id"),
            {"task_id": DELETED_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 0, "Deleted task should have been removed from task_latest"

        result = connection.execute(
            sa.text("SELECT COUNT(*) FROM task WHERE object_id = :task_id"),
            {"task_id": DELETED_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 0, "Deleted task should have been removed from task"

        # Deleted task WITH workspace_id should be preserved in both tables
        result = connection.execute(
            sa.text("SELECT COUNT(*) FROM task_latest WHERE object_id = :task_id"),
            {"task_id": DELETED_WITH_WS_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1, "Deleted task with workspace_id should NOT have been removed from task_latest"

        result = connection.execute(
            sa.text("SELECT COUNT(*) FROM task WHERE object_id = :task_id"),
            {"task_id": DELETED_WITH_WS_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1, "Deleted task with workspace_id should NOT have been removed from task"

        # Active task should be unaffected
        result = connection.execute(
            sa.text("""
                SELECT json_extract(current_state, '$.workspace_id')
                FROM task_latest
                WHERE object_id = :task_id
            """),
            {"task_id": ACTIVE_TASK_ID},
        )
        row = result.fetchone()
        assert row is not None, "Active task not found in task_latest"
        assert row[0] == "ws-existing-1", f"Active task's workspace_id was changed to {row[0]}"
