import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"


class TestRemoveCompactAndClearContextMessages(MigrationTestFixture):
    """Test fixture for the migration that removes CompactTaskUserMessage, ClearContextUserMessage, and ContextClearedMessage rows."""

    @property
    def revision(self) -> str:
        return "b9e29dc159f6"

    @property
    def down_revision(self) -> str:
        return "a1b2c3d4e5f7"

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

        messages = [
            ("snap-msg-1", "msg-1", "CompactTaskUserMessage", "USER"),
            ("snap-msg-2", "msg-2", "ClearContextUserMessage", "USER"),
            ("snap-msg-3", "msg-3", "ContextClearedMessage", "AGENT"),
            ("snap-msg-4", "msg-4", "ChatInputUserMessage", "USER"),
        ]
        for snapshot_id, msg_id, object_type, source in messages:
            message = json.dumps(
                {
                    "object_type": object_type,
                    "message_id": msg_id,
                }
            )
            connection.execute(
                sa.text("""
                    INSERT INTO saved_agent_message (
                        snapshot_id, created_at, object_id, task_id,
                        message, source, is_partial
                    ) VALUES (
                        :snapshot_id, '2026-01-01T00:00:00', :object_id, :task_id,
                        :message, :source, 0
                    )
                """),
                {
                    "snapshot_id": snapshot_id,
                    "object_id": msg_id,
                    "task_id": TASK_ID,
                    "message": message,
                    "source": source,
                },
            )

    def verify(self, connection: sa.engine.Connection) -> None:
        result = connection.execute(sa.text("SELECT json_extract(message, '$.object_type') FROM saved_agent_message"))
        remaining_types = [row[0] for row in result]
        assert remaining_types == ["ChatInputUserMessage"], (
            f"Expected only ChatInputUserMessage, got {remaining_types}"
        )
