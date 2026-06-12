"""add harness to Workspace

Revision ID: 587b6b6e8747
Revises: 6ab148aeec31
Create Date: 2026-05-29 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "587b6b6e8747"
down_revision: str | None = "6ab148aeec31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "workspace",
        sa.Column("harness", sa.String(), nullable=False, server_default="claude"),
    )
    op.add_column(
        "workspace_latest",
        sa.Column("harness", sa.String(), nullable=False, server_default="claude"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("workspace_latest", "harness")
    op.drop_column("workspace", "harness")
