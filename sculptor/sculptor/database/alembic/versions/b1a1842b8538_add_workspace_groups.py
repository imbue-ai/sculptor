"""add workspace groups

Creates the workspace_group / workspace_group_latest pair (the standard
automanaged two-table pattern) and adds the nullable group_id membership
column to workspace / workspace_latest. Membership lives on the workspace so
a workspace structurally belongs to at most one group.

Revision ID: b1a1842b8538
Revises: 6026c03dc852
Create Date: 2026-07-07 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a1842b8538"
down_revision: str | None = "6026c03dc852"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workspace_group",
        sa.Column("snapshot_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("organization_reference", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("created_via_cli", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_table(
        "workspace_group_latest",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("organization_reference", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("created_via_cli", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project_latest.object_id"],
            name="foreign_key_workspace_group_project_id",
        ),
        sa.PrimaryKeyConstraint("object_id"),
    )
    op.add_column("workspace", sa.Column("group_id", sa.String(), nullable=True))
    op.add_column("workspace_latest", sa.Column("group_id", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("workspace_latest", "group_id")
    op.drop_column("workspace", "group_id")
    op.drop_table("workspace_group_latest")
    op.drop_table("workspace_group")
