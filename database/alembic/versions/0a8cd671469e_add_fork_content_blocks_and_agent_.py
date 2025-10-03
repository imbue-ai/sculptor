"""add fork content blocks and agent message

Revision ID: 0a8cd671469e
Revises: 34970e9efebc
Create Date: 2025-10-01 14:31:31.595468

"""

import json
from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a8cd671469e"
down_revision: str | None = "34970e9efebc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # Find all ForkAgentUserMessage messages
    result = bind.execute(
        sa.text("""
            SELECT snapshot_id, message
            FROM saved_agent_message
            WHERE json_extract(message, '$.object_type') = 'ForkAgentUserMessage'
        """)
    )

    messages = result.fetchall()
    all_updates = []

    for snapshot_id, message_json in messages:
        message = json.loads(message_json)
        # Rename the object_type
        message["object_type"] = "ForkAgentSystemMessage"
        all_updates.append({"snapshot_id": snapshot_id, "message": json.dumps(message)})

    if all_updates:
        bind.execute(
            sa.text("UPDATE saved_agent_message SET message = :message WHERE snapshot_id = :snapshot_id"),
            all_updates,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    # Revert ForkAgentSystemMessage back to ForkAgentUserMessage
    result = bind.execute(
        sa.text("""
            SELECT snapshot_id, message
            FROM saved_agent_message
            WHERE json_extract(message, '$.object_type') = 'ForkAgentSystemMessage'
        """)
    )

    messages = result.fetchall()
    all_updates = []

    for snapshot_id, message_json in messages:
        message = json.loads(message_json)
        # Revert the object_type
        message["object_type"] = "ForkAgentUserMessage"
        all_updates.append({"snapshot_id": snapshot_id, "message": json.dumps(message)})

    if all_updates:
        bind.execute(
            sa.text("UPDATE saved_agent_message SET message = :message WHERE snapshot_id = :snapshot_id"),
            all_updates,
        )
