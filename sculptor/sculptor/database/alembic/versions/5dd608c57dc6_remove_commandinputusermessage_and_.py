"""Remove CommandInputUserMessage and related message types

Revision ID: 5dd608c57dc6
Revises: 811610e55bae
Create Date: 2026-02-02 16:43:37.260595

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5dd608c57dc6"
down_revision: str | None = "811610e55bae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove messages with no longer supported message types.
    # These message types were never actually used in production, but we clean them up
    # to ensure schema consistency and prevent deserialization errors.
    connection = op.get_bind()

    # Delete messages with CommandInputUserMessage or UserCommandFailureAgentMessage type
    # Note: saved_agent_message does not have a _latest table (is_dual_table=False)
    connection.execute(
        sa.text("""
            DELETE FROM saved_agent_message
            WHERE json_extract(message, '$.object_type') IN ('CommandInputUserMessage', 'UserCommandFailureAgentMessage')
        """)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Cannot restore deleted messages
    pass
