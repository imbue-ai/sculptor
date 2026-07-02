import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"
MESSAGE_ID = "msg-test-1"


class TestAddRecentToolSummariesToWorkflowAgentProgress(MigrationTestFixture):
    """Test that adding recent_tool_summaries to WorkflowAgentProgress preserves existing messages.

    This is a no-op migration (JSON schema change only — the field defaults
    to an empty tuple). The test verifies that saved_agent_message rows
    carrying a workflow notification with final_workflow_entries survive the
    migration unchanged.
    """

    @property
    def revision(self) -> str:
        return "5cb094ae1d22"

    @property
    def down_revision(self) -> str:
        return "4a289e39dd87"

    def seed(self, connection: sa.engine.Connection) -> None:
        connection.execute(
            sa.text("""
                INSERT INTO project_latest (
                    created_at, object_id, organization_reference,
                    name, user_git_repo_url, is_path_accessible,
                    is_deleted, default_system_prompt
                ) VALUES (
                    '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', NULL, 1, 0, NULL
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
                INSERT INTO task_latest (
                    created_at, object_id, organization_reference,
                    user_reference, project_id, input_data,
                    max_seconds, current_state, outcome, error,
                    is_deleted, is_deleting, last_read_at
                ) VALUES (
                    '2026-01-01T00:00:00', :task_id, 'org-1',
                    'user-1', :project_id, :input_data,
                    NULL, NULL, 'PENDING', NULL,
                    0, 0, NULL
                )
            """),
            {
                "task_id": TASK_ID,
                "project_id": PROJECT_ID,
                "input_data": input_data,
            },
        )

        # Insert a workflow notification whose agent entries predate
        # recent_tool_summaries
        message = json.dumps(
            {
                "object_type": "BackgroundTaskNotificationAgentMessage",
                "message_id": MESSAGE_ID,
                "background_task_id": "task-bg-1",
                "tool_use_id": "toolu-bg-1",
                "status": "completed",
                "summary": "done",
                "workflow_name": "review",
                "final_workflow_entries": [
                    {"object_type": "WorkflowPhaseProgress", "index": 0, "title": "Review"},
                    {"object_type": "WorkflowAgentProgress", "index": 0, "label": "review:bugs", "state": "done"},
                ],
            }
        )
        connection.execute(
            sa.text("""
                INSERT INTO saved_agent_message (
                    snapshot_id, created_at, object_id, task_id,
                    message, source, is_partial
                ) VALUES (
                    'snap-msg-1', '2026-01-01T00:00:00', :object_id, :task_id,
                    :message, 'AGENT', 0
                )
            """),
            {
                "object_id": MESSAGE_ID,
                "task_id": TASK_ID,
                "message": message,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        result = connection.execute(
            sa.text("SELECT message FROM saved_agent_message WHERE object_id = :object_id"),
            {"object_id": MESSAGE_ID},
        )
        row = result.fetchone()
        assert row is not None, "BackgroundTaskNotificationAgentMessage not found after migration"

        data = json.loads(row[0])
        assert data["object_type"] == "BackgroundTaskNotificationAgentMessage"
        assert len(data["final_workflow_entries"]) == 2
