"""add index on saved_agent_message.task_id

Each startup query filters saved_agent_message by task_id, but there
was no index — causing full table scans on every lookup. Adding a
composite index on (task_id, created_at) covers both the WHERE filter
and the ORDER BY clause used in get_messages_for_task.

Revision ID: 0bf9b0c50c83
Revises: bcc42be33ebc
Create Date: 2026-03-31 00:00:00.000000

"""

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0bf9b0c50c83"
down_revision: str | None = "bcc42be33ebc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_saved_agent_message_task_id_created_at",
        "saved_agent_message",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_saved_agent_message_task_id_created_at", table_name="saved_agent_message")
