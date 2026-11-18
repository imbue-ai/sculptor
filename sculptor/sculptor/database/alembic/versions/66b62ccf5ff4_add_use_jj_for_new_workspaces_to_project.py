"""add use_jj_for_new_workspaces to project

Revision ID: 66b62ccf5ff4
Revises: 6026c03dc852
Create Date: 2026-11-16 14:46:44.806579

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "66b62ccf5ff4"
down_revision: str | None = "6026c03dc852"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("project", sa.Column("use_jj_for_new_workspaces", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "project_latest", sa.Column("use_jj_for_new_workspaces", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("project_latest", "use_jj_for_new_workspaces")
    op.drop_column("project", "use_jj_for_new_workspaces")
