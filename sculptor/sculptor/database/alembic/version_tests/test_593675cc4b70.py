import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"
MESSAGE_ID = "msg-test-1"


class TestAddPlanModeFieldsToChatInputUserMessage(MigrationTestFixture):
    """Test that adding enter_plan_mode and exit_plan_mode to ChatInputUserMessage preserves existing messages.

    This is a no-op migration (JSON schema change only). The test verifies
    that saved_agent_message rows with ChatInputUserMessage data survive
    the migration unchanged.
    """

    @property
    def revision(self) -> str:
        return "593675cc4b70"

    @property
    def down_revision(self) -> str:
        return "b1a2c3d4e5f6"

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

        # Insert a task
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

        # Insert a ChatInputUserMessage without the new plan mode fields
        message = json.dumps(
            {
                "object_type": "ChatInputUserMessage",
                "message_id": MESSAGE_ID,
            }
        )
        connection.execute(
            sa.text("""
                INSERT INTO saved_agent_message (
                    snapshot_id, created_at, object_id, task_id,
                    message, source, is_partial
                ) VALUES (
                    'snap-msg-1', '2026-01-01T00:00:00', :object_id, :task_id,
                    :message, 'USER', 0
                )
            """),
            {
                "object_id": MESSAGE_ID,
                "task_id": TASK_ID,
                "message": message,
            },
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Verify the ChatInputUserMessage is preserved
        result = connection.execute(
            sa.text("SELECT message FROM saved_agent_message WHERE object_id = :object_id"),
            {"object_id": MESSAGE_ID},
        )
        row = result.fetchone()
        assert row is not None, "ChatInputUserMessage not found after migration"

        data = json.loads(row[0])
        assert data["object_type"] == "ChatInputUserMessage"
        assert data["message_id"] == MESSAGE_ID
