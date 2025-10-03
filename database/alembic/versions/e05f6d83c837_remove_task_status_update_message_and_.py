"""remove task status update message and remove last_handled_message_id

Revision ID: e05f6d83c837
Revises: 8a4050464872
Create Date: 2025-08-18 15:26:54.850942

"""

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e05f6d83c837"
down_revision: str | None = "8a4050464872"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        DELETE FROM saved_agent_message
        WHERE json_extract(message, '$.object_type') = 'TaskStatusUpdateAgentMessage'
    """)

    # Remove last_handled_message_id from AgentTaskStateV1 in task.current_state
    op.execute("""
        UPDATE task
        SET current_state = json_remove(current_state, '$.last_handled_message_id')
        WHERE json_extract(current_state, '$.object_type') = 'AgentTaskStateV1'
          AND json_extract(current_state, '$.last_handled_message_id') IS NOT NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
