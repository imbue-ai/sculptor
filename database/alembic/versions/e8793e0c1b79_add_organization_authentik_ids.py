"""add_organization_authentik_ids

Revision ID: e8793e0c1b79
Revises: 9dae61b23a22
Create Date: 2025-07-23 11:07:42.699507

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import context
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8793e0c1b79"
down_revision: str | None = "9dae61b23a22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    dialect_name = context.get_context().dialect.name
    if dialect_name == "sqlite":
        op.execute("PRAGMA foreign_keys=OFF;")
        # SQLite does not support ALTER statements so we need to work around using the batch mode.
        # We need to drop the triggers - they will be recreated next time the application starts.
        op.execute("DROP TRIGGER IF EXISTS organization_before_insert;")
        op.execute("DROP TRIGGER IF EXISTS set_organization_created_at;")
        with op.batch_alter_table("organization") as batch_op:
            batch_op.add_column(sa.Column("authentik_id", sa.String(), nullable=True))
        with op.batch_alter_table("organization_latest") as batch_op:
            batch_op.add_column(sa.Column("authentik_id", sa.String(), nullable=True))
            batch_op.create_unique_constraint("unique_organization_authentik_id", ["authentik_id"])
        op.execute("PRAGMA foreign_keys=ON;")
    else:
        op.add_column("organization", sa.Column("authentik_id", sa.String(), nullable=True))
        op.add_column("organization_latest", sa.Column("authentik_id", sa.String(), nullable=True))
        op.create_unique_constraint("unique_organization_authentik_id", "organization_latest", ["authentik_id"])
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    dialect_name = context.get_context().dialect.name
    if dialect_name == "sqlite":
        op.execute("PRAGMA foreign_keys=OFF;")
        op.execute("DROP TRIGGER IF EXISTS organization_before_insert;")
        op.execute("DROP TRIGGER IF EXISTS set_organization_created_at;")
        with op.batch_alter_table("organization_latest") as batch_op:
            batch_op.drop_constraint("unique_organization_authentik_id", type_="unique")
            batch_op.drop_column("authentik_id")
        with op.batch_alter_table("organization") as batch_op:
            batch_op.drop_column("authentik_id")
        op.execute("PRAGMA foreign_keys=ON;")
    else:
        op.drop_constraint("unique_organization_authentik_id", "organization_latest", type_="unique")
        op.drop_column("organization_latest", "authentik_id")
        op.drop_column("organization", "authentik_id")
