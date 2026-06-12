"""backfill setup_status from legacy setup_command_triggered

Translates the legacy ``setup_command_triggered`` boolean into the new
``setup_status`` column for pre-existing workspaces. Workspaces that
already ran setup under the old PTY-based implementation land in
``succeeded`` so they will not auto-rerun under the new subprocess
runner. Every other pre-existing workspace lands in ``not_configured``
— even if its project has a command configured now. The migration
must never auto-fire setup on a workspace that the user did not
explicitly opt into; the user can click the Run-setup affordance on
the SetupStatusCard if they want a manual run.

Revision ID: 35cc9f0245b6
Revises: b5a4106e6118
Create Date: 2026-04-27 14:20:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "35cc9f0245b6"
down_revision: str | None = "b5a4106e6118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    for table in ("workspace", "workspace_latest"):
        connection.execute(sa.text(f"UPDATE {table} SET setup_status = 'succeeded' WHERE setup_command_triggered = 1"))
        connection.execute(
            sa.text(f"UPDATE {table} SET setup_status = 'not_configured' WHERE setup_command_triggered = 0")
        )


def downgrade() -> None:
    """No downgrade — cannot reliably reverse the legacy-flag derivation."""
    pass
