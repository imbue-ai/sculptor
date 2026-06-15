"""backfill target_branch default for existing workspaces

Workspaces created before automatic target-branch resolution have a
NULL or empty target_branch.  The old code silently fell back to
"origin/main" via ``workspace.target_branch or "origin/main"``.
This migration makes that implicit default explicit so the new code
(which no longer hard-codes a fallback) sees the correct value.

Revision ID: bcc42be33ebc
Revises: eedceaef0697
Create Date: 2026-03-27 11:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bcc42be33ebc"
down_revision: str | None = "eedceaef0697"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TARGET_BRANCH = "origin/main"
TABLE_NAMES = ("workspace", "workspace_latest")


def upgrade() -> None:
    """Set target_branch to 'origin/main' for workspaces that have NULL or empty values."""
    connection = op.get_bind()
    for table_name in TABLE_NAMES:
        connection.execute(
            sa.text(
                f"UPDATE {table_name} SET target_branch = :default_branch WHERE target_branch IS NULL OR target_branch = ''"
            ).bindparams(sa.bindparam("default_branch", DEFAULT_TARGET_BRANCH))
        )


def downgrade() -> None:
    """No downgrade — cannot distinguish originally-NULL from explicitly-set values."""
    pass
