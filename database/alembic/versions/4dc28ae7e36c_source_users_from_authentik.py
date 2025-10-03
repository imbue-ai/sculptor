"""source_users_from_authentik

Revision ID: 4dc28ae7e36c
Revises: f522cdff22d8
Create Date: 2025-07-04 14:11:44.576745

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import context
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4dc28ae7e36c"
down_revision: str | None = "f522cdff22d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    dialect_name = context.get_context().dialect.name
    if dialect_name == "sqlite":
        op.execute("PRAGMA foreign_keys=OFF;")
        # SQLite does not support ALTER statements so we need to work around using the batch mode.
        # We need to drop the triggers - they will be recreated next time the application starts.
        op.execute("DROP TRIGGER IF EXISTS user_before_insert;")
        op.execute("DROP TRIGGER IF EXISTS set_user_created_at;")
        with op.batch_alter_table("user") as batch_op:
            batch_op.add_column(sa.Column("authentik_id", sa.String(), nullable=True))
        with op.batch_alter_table("user_latest") as batch_op:
            batch_op.add_column(sa.Column("authentik_id", sa.String(), nullable=True))
            batch_op.create_unique_constraint("unique_user_authentik_id", ["authentik_id"])
        op.execute("PRAGMA foreign_keys=ON;")
    else:
        op.add_column("user", sa.Column("authentik_id", sa.String(), nullable=True))
        op.add_column("user_latest", sa.Column("authentik_id", sa.String(), nullable=True))
        op.create_unique_constraint("unique_user_authentik_id", "user_latest", ["authentik_id"])


def downgrade() -> None:
    """Downgrade schema."""
    dialect_name = context.get_context().dialect.name
    if dialect_name == "sqlite":
        # SQLite does not support ALTER statements so we need to work around using the batch mode.
        op.execute("PRAGMA foreign_keys=OFF;")
        op.execute("DROP TRIGGER IF EXISTS user_before_insert;")
        op.execute("DROP TRIGGER IF EXISTS set_user_created_at;")
        with op.batch_alter_table("user_latest") as batch_op:
            batch_op.drop_constraint("unique_user_authentik_id", type_="unique")
            batch_op.drop_column("authentik_id")
        with op.batch_alter_table("user") as batch_op:
            batch_op.drop_column("authentik_id")
        op.execute("PRAGMA foreign_keys=ON;")
    else:
        op.drop_constraint("unique_user_authentik_id", "user_latest", type_="unique")
        op.drop_column("user_latest", "authentik_id")
        op.drop_column("user", "authentik_id")
