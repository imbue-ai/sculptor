"""drop harness from Workspace

Agent type is a per-agent property carried on each task's agent_config;
the workspace-bound harness selection is gone.

Revision ID: b3f1a9c2d6e5
Revises: 587b6b6e8747
Create Date: 2026-06-11 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f1a9c2d6e5"
down_revision: str | None = "587b6b6e8747"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("workspace", "harness")
    op.drop_column("workspace_latest", "harness")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "workspace",
        sa.Column("harness", sa.String(), nullable=False, server_default="claude"),
    )
    op.add_column(
        "workspace_latest",
        sa.Column("harness", sa.String(), nullable=False, server_default="claude"),
    )
