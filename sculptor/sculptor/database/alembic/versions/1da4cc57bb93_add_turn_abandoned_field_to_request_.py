"""add turn_abandoned field to request success messages

No SQL changes are needed — the new field lives inside the saved-message
JSON blob and defaults to False, so existing data is unaffected.

Revision ID: 1da4cc57bb93
Revises: 5cb094ae1d22
Create Date: 2026-07-09 20:14:08.657965

"""

from typing import Sequence

# revision identifiers, used by Alembic.
revision: str = "1da4cc57bb93"
down_revision: str | None = "5cb094ae1d22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema changes: the new field lives inside JSON blobs and defaults to False."""
    pass


def downgrade() -> None:
    """No schema changes to reverse."""
    pass
