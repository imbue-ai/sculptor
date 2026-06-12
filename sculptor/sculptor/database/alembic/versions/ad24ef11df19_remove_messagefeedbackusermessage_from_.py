"""Remove MessageFeedbackUserMessage from PersistentUserMessageUnion

Revision ID: ad24ef11df19
Revises: 811610e55bae
Create Date: 2026-02-10 08:38:43.353572

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ad24ef11df19"
down_revision: str | None = "a53ed60690f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OBJECT_TYPE = "MessageFeedbackUserMessage"
TABLE_NAME = "saved_agent_message"


def upgrade() -> None:
    """Delete all MessageFeedbackUserMessage rows since the type has been removed."""
    connection = op.get_bind()
    connection.execute(
        sa.text(f"DELETE FROM {TABLE_NAME} WHERE json_extract(message, '$.object_type') = :target").bindparams(
            sa.bindparam("target", OBJECT_TYPE)
        ),
    )


def downgrade() -> None:
    """No downgrade possible - feedback messages cannot be recreated."""
    pass
