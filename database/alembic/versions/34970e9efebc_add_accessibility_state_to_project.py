"""add accessibility state to project

Revision ID: 34970e9efebc
Revises: 89389e1b9e5c
Create Date: 2025-09-29 16:22:58.203103

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "34970e9efebc"
down_revision: str | None = "89389e1b9e5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add is_path_accessible column with default value of 1 (True)
    # Using server_default for both PostgreSQL and SQLite compatibility
    op.add_column("project", sa.Column("is_path_accessible", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("project_latest", sa.Column("is_path_accessible", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the is_path_accessible columns
    op.drop_column("project_latest", "is_path_accessible")
    op.drop_column("project", "is_path_accessible")
