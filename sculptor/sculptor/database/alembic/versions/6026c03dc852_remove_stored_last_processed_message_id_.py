"""remove stored last_processed_message_id from agent task state

No SQL changes are needed — the field lived inside the task-state JSON blob
and is now derived from the persisted message log at runtime. Old rows that
still carry the key validate fine: the extra key is ignored on validate.

Revision ID: 6026c03dc852
Revises: 1da4cc57bb93
Create Date: 2026-07-09 21:34:57.331510

"""

from typing import Sequence

# revision identifiers, used by Alembic.
revision: str = "6026c03dc852"
down_revision: str | None = "1da4cc57bb93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema changes: the removed field lived inside JSON blobs and is ignored on validate."""
    pass


def downgrade() -> None:
    """No schema changes to reverse."""
    pass
