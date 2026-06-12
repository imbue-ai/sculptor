"""drop parent_task_id column

Revision ID: a53ed60690f5
Revises: 5dd608c57dc6
Create Date: 2026-02-10 08:19:28.547223

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a53ed60690f5"
down_revision: str | None = "5dd608c57dc6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the parent_task_id column and its foreign key from task tables."""
    connection = op.get_bind()

    # Drop triggers that reference task_latest before batch_alter_table.
    # SQLite 3.25+ validates schema consistency during ALTER TABLE RENAME,
    # and batch_alter_table internally does DROP + RENAME. If the trigger
    # references task_latest while it's temporarily dropped, the rename fails
    # with "no such table: main.task_latest".
    # The triggers are recreated by initialize_db() on next Sculptor startup.
    connection.execute(sa.text("DROP TRIGGER IF EXISTS task_before_insert"))
    connection.execute(sa.text("DROP TRIGGER IF EXISTS set_task_created_at"))

    # task_latest requires batch_alter_table because SQLite's native DROP COLUMN
    # refuses to drop a column referenced by a foreign key constraint.
    with op.batch_alter_table("task_latest", schema=None) as batch_op:
        batch_op.drop_constraint("foreign_key_parent_task_id", type_="foreignkey")
        batch_op.drop_column("parent_task_id")

    # task has no FK on parent_task_id, so native DROP COLUMN works.
    connection.execute(sa.text("ALTER TABLE task DROP COLUMN parent_task_id"))


def downgrade() -> None:
    """Re-add parent_task_id column to task tables."""
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_task_id", sa.String(), nullable=True))

    with op.batch_alter_table("task_latest", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_task_id", sa.String(), nullable=True))
        batch_op.create_foreign_key("foreign_key_parent_task_id", "task_latest", ["parent_task_id"], ["object_id"])
