"""add last_read_at to task

Revision ID: 2755d9e9f872
Revises: 8522ec5edc2a
Create Date: 2026-02-18 16:10:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2755d9e9f872"
down_revision: str | None = "8522ec5edc2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("task", sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_latest", sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("task_latest", "last_read_at")
    op.drop_column("task", "last_read_at")
