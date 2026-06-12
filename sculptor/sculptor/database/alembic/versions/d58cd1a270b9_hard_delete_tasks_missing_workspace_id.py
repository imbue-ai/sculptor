"""hard-delete tasks missing workspace_id

The 811610e55bae migration only added workspace_id to non-deleted tasks.
After the delete-task refactor started using get_all_tasks() (which loads
every row including deleted ones), deserialization fails for deleted
AgentTaskStateV2 rows that are missing workspace_id.

Since deleted tasks cannot be restored, we simply hard-delete them from
both the task and task_latest tables.

Revision ID: d58cd1a270b9
Revises: 593675cc4b70
Create Date: 2026-03-06 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d58cd1a270b9"
down_revision: str | None = "593675cc4b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Hard-delete AgentTaskStateV2 tasks that are missing workspace_id.

    These are deleted tasks that were skipped by the original 811610e55bae migration
    (which only backfilled non-deleted tasks). Since deleted tasks cannot be restored,
    it is safe to remove them entirely.
    """
    connection = op.get_bind()

    connection.execute(
        sa.text("""
            DELETE FROM task_latest
            WHERE is_deleted = 1
            AND json_extract(current_state, '$.object_type') = 'AgentTaskStateV2'
            AND json_extract(current_state, '$.workspace_id') IS NULL
        """)
    )

    connection.execute(
        sa.text("""
            DELETE FROM task
            WHERE is_deleted = 1
            AND json_extract(current_state, '$.object_type') = 'AgentTaskStateV2'
            AND json_extract(current_state, '$.workspace_id') IS NULL
        """)
    )


def downgrade() -> None:
    """No downgrade — the removed rows were already soft-deleted and unrecoverable."""
