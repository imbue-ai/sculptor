import json

import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
TASK_ID = "task-test-1"


class TestRemoveMessageFeedbackUserMessage(MigrationTestFixture):
    """Test fixture for the migration that removes MessageFeedbackUserMessage rows."""

    @property
    def revision(self) -> str:
        return "ad24ef11df19"

    @property
    def down_revision(self) -> str:
        return "a53ed60690f5"

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

        # Insert a task (after a53ed60690f5, parent_task_id is dropped from task_latest)
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

        messages = [
            ("snap-msg-1", "msg-1", "MessageFeedbackUserMessage"),
            ("snap-msg-2", "msg-2", "ChatInputUserMessage"),
        ]
        for snapshot_id, msg_id, object_type in messages:
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
                        :message, 'USER', 0
                    )
                """),
                {
                    "snapshot_id": snapshot_id,
                    "object_id": msg_id,
                    "task_id": TASK_ID,
                    "message": message,
                },
            )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Check MessageFeedbackUserMessage row is deleted
        result = connection.execute(sa.text("SELECT json_extract(message, '$.object_type') FROM saved_agent_message"))
        remaining_types = [row[0] for row in result]
        assert remaining_types == ["ChatInputUserMessage"], (
            f"Expected only ChatInputUserMessage, got {remaining_types}"
        )
