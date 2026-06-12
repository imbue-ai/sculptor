"""Remove CompactTaskUserMessage, ClearContextUserMessage, and ContextClearedMessage

Revision ID: b9e29dc159f6
Revises: a1b2c3d4e5f7
Create Date: 2026-04-23 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9e29dc159f6"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOVED_OBJECT_TYPES = ("CompactTaskUserMessage", "ClearContextUserMessage", "ContextClearedMessage")
TABLE_NAME = "saved_agent_message"


def upgrade() -> None:
    """Delete rows with removed message types to prevent deserialization errors."""
    connection = op.get_bind()
    connection.execute(
        sa.text(f"DELETE FROM {TABLE_NAME} WHERE json_extract(message, '$.object_type') IN :types").bindparams(
            sa.bindparam("types", REMOVED_OBJECT_TYPES, expanding=True)
        ),
    )


def downgrade() -> None:
    """No downgrade possible - deleted messages cannot be recreated."""
    pass
