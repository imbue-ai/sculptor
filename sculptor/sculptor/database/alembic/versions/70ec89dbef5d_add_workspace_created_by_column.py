"""add workspace created_by attribution column

Revision ID: 70ec89dbef5d
Revises: 6026c03dc852
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "70ec89dbef5d"
down_revision: str | None = "6026c03dc852"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # created_by stores an embedded CreationAttribution object (JSON), not an FK.
    # Added to both the `workspace` and `workspace_latest` tables per the
    # two-table trigger design.
    op.add_column("workspace", sa.Column("created_by", sa.JSON(), nullable=True))
    op.add_column("workspace_latest", sa.Column("created_by", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("workspace_latest", "created_by")
    op.drop_column("workspace", "created_by")
