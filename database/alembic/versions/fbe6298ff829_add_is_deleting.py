"""add is deleting

Revision ID: fbe6298ff829
Revises: bde63d1fb395
Create Date: 2025-09-16 15:00:09.369662

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fbe6298ff829"
down_revision: str | None = "bde63d1fb395"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("task", sa.Column("is_deleting", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task_latest", sa.Column("is_deleting", sa.Integer(), nullable=False, server_default="0"))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("task_latest", "is_deleting")
    op.drop_column("task", "is_deleting")
    # ### end Alembic commands ###
