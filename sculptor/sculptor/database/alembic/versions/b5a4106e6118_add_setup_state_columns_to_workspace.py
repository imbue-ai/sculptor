"""add setup state columns to workspace

Revision ID: b5a4106e6118
Revises: c8d4e5f6a7b8
Create Date: 2026-04-27 14:11:45.667093

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5a4106e6118"
down_revision: str | None = "059f36aaa193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("workspace", sa.Column("setup_status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("workspace", sa.Column("setup_run_id", sa.String(), nullable=True))
    op.add_column("workspace", sa.Column("setup_exit_code", sa.Integer(), nullable=True))
    op.add_column("workspace", sa.Column("setup_started_at", sa.Float(), nullable=True))
    op.add_column("workspace", sa.Column("setup_finished_at", sa.Float(), nullable=True))
    op.add_column("workspace", sa.Column("setup_log_path", sa.String(), nullable=True))
    op.add_column("workspace", sa.Column("setup_log_truncated", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("workspace_latest", sa.Column("setup_status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("workspace_latest", sa.Column("setup_run_id", sa.String(), nullable=True))
    op.add_column("workspace_latest", sa.Column("setup_exit_code", sa.Integer(), nullable=True))
    op.add_column("workspace_latest", sa.Column("setup_started_at", sa.Float(), nullable=True))
    op.add_column("workspace_latest", sa.Column("setup_finished_at", sa.Float(), nullable=True))
    op.add_column("workspace_latest", sa.Column("setup_log_path", sa.String(), nullable=True))
    op.add_column(
        "workspace_latest",
        sa.Column("setup_log_truncated", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("workspace_latest", "setup_log_truncated")
    op.drop_column("workspace_latest", "setup_log_path")
    op.drop_column("workspace_latest", "setup_finished_at")
    op.drop_column("workspace_latest", "setup_started_at")
    op.drop_column("workspace_latest", "setup_exit_code")
    op.drop_column("workspace_latest", "setup_run_id")
    op.drop_column("workspace_latest", "setup_status")
    op.drop_column("workspace", "setup_log_truncated")
    op.drop_column("workspace", "setup_log_path")
    op.drop_column("workspace", "setup_finished_at")
    op.drop_column("workspace", "setup_started_at")
    op.drop_column("workspace", "setup_exit_code")
    op.drop_column("workspace", "setup_run_id")
    op.drop_column("workspace", "setup_status")
