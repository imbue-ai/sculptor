"""drop archive columns from task

Revision ID: 865d3a5b4f84
Revises: 2755d9e9f872
Create Date: 2026-02-19 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "865d3a5b4f84"
down_revision: str | None = "2755d9e9f872"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    # Drop triggers that reference the task table before dropping columns.
    # SQLite validates trigger references during ALTER TABLE, so the triggers
    # would cause the DROP COLUMN to fail.
    # The triggers are recreated by initialize_db() on next Sculptor startup.
    connection.execute(sa.text("DROP TRIGGER IF EXISTS task_before_insert"))
    connection.execute(sa.text("DROP TRIGGER IF EXISTS set_task_created_at"))

    op.drop_column("task", "is_archived")
    op.drop_column("task", "is_archiving")
    op.drop_column("task_latest", "is_archived")
    op.drop_column("task_latest", "is_archiving")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("task", sa.Column("is_archived", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task", sa.Column("is_archiving", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task_latest", sa.Column("is_archived", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task_latest", sa.Column("is_archiving", sa.Integer(), nullable=False, server_default="0"))
