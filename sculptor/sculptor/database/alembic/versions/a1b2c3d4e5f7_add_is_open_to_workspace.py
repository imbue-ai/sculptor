"""add is_open to workspace

Revision ID: a1b2c3d4e5f7
Revises: f9c8fbb043ec
Create Date: 2026-04-15 14:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "f9c8fbb043ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("workspace", sa.Column("is_open", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("workspace_latest", sa.Column("is_open", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("workspace_latest", "is_open")
    op.drop_column("workspace", "is_open")
