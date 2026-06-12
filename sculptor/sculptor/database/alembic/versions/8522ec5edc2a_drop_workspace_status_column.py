"""drop_workspace_status_column

Revision ID: 8522ec5edc2a
Revises: 20fea77a3f5a
Create Date: 2026-02-12 20:44:02.081284

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8522ec5edc2a"
down_revision: str | None = "20fea77a3f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    # Drop triggers that reference the workspace table before dropping the column.
    # SQLite validates trigger references during ALTER TABLE, so the trigger
    # referencing NEW.status would cause the DROP COLUMN to fail.
    # The triggers are recreated by initialize_db() on next Sculptor startup.
    connection.execute(sa.text("DROP TRIGGER IF EXISTS workspace_before_insert"))
    connection.execute(sa.text("DROP TRIGGER IF EXISTS set_workspace_created_at"))

    op.drop_column("workspace", "status")
    op.drop_column("workspace_latest", "status")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("workspace", sa.Column("status", sa.VARCHAR(), nullable=False, server_default="ACTIVE"))
    op.add_column("workspace_latest", sa.Column("status", sa.VARCHAR(), nullable=False, server_default="ACTIVE"))
