"""MIGRATION_MESSAGE=made LLMModel not nullable in ChatInputUserMessage

Revision ID: 37411143b314
Revises: 444c63d27956
Create Date: 2025-08-14 16:26:32.506239

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "37411143b314"
down_revision: str | None = "444c63d27956"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Update all ChatInputUserMessage objects in saved_agent_message table
    # to have model_name set to CLAUDE-4-SONNET where it's currently null

    # Get database connection
    conn = op.get_bind()

    # Query all saved_agent_message rows
    result = conn.execute(sa.text("SELECT snapshot_id, message FROM saved_agent_message"))

    # Process each row
    import json

    updates = []
    for row in result:
        snapshot_id = row[0]
        message_json = json.loads(row[1])

        # Check if this is a ChatInputUserMessage and model_name is null
        if message_json.get("object_type") == "ChatInputUserMessage" and message_json.get("model_name") is None:
            # Update the model_name to CLAUDE-4-SONNET
            message_json["model_name"] = "CLAUDE-4-SONNET"
            updates.append({"snapshot_id": snapshot_id, "message": json.dumps(message_json)})

    # Apply updates if any
    if updates:
        conn.execute(
            sa.text("UPDATE saved_agent_message SET message = :message WHERE snapshot_id = :snapshot_id"), updates
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Make LLMModel nullable again - no data migration needed since null is allowed
