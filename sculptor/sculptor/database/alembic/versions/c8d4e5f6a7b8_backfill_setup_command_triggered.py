"""backfill setup_command_triggered for pre-existing workspaces

Workspaces created before this migration have ``setup_command_triggered =
False`` regardless of whether the experimental setup-commands toggle was
ever enabled. When a user turns the toggle on and configures a setup
command, ``agent_environment_context`` would retroactively inject the setup
command into every pre-existing workspace's terminal. Treat all workspaces
that exist at upgrade time as already set up so the toggle only affects
workspaces created after it was enabled.

Revision ID: c8d4e5f6a7b8
Revises: b9e29dc159f6
Create Date: 2026-04-22 19:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d4e5f6a7b8"
down_revision: str | None = "b9e29dc159f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("workspace", "workspace_latest")
SETUP_COMMAND_TRIGGERED = True


def upgrade() -> None:
    """Mark all pre-existing workspaces as already set up so the toggle only affects later workspaces."""
    connection = op.get_bind()
    for table_name in TABLE_NAMES:
        connection.execute(
            sa.text(f"UPDATE {table_name} SET setup_command_triggered = :is_triggered").bindparams(
                sa.bindparam("is_triggered", SETUP_COMMAND_TRIGGERED)
            )
        )


def downgrade() -> None:
    """No downgrade — cannot distinguish originally-False from backfilled values."""
    pass
