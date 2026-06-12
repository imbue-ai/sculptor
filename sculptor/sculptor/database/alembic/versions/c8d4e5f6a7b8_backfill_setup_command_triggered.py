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


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE workspace SET setup_command_triggered = 1"))
    connection.execute(sa.text("UPDATE workspace_latest SET setup_command_triggered = 1"))


def downgrade() -> None:
    """No downgrade — cannot distinguish originally-False from backfilled values."""
    pass
