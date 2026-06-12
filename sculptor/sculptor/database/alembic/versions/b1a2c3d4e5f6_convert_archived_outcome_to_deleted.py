"""convert archived outcome to deleted

Revision ID: b1a2c3d4e5f6
Revises: 0fb6dc48c8ef
Create Date: 2026-02-23 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: str | None = "0fb6dc48c8ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert any remaining ARCHIVED outcomes to DELETED.

    Migration 865d3a5b4f84 dropped the archive columns but did not convert
    existing outcome='ARCHIVED' rows. This migration fixes databases that
    already ran the broken version.
    """
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE task SET outcome = 'DELETED' WHERE outcome = 'ARCHIVED'"))
    connection.execute(sa.text("UPDATE task_latest SET outcome = 'DELETED' WHERE outcome = 'ARCHIVED'"))


def downgrade() -> None:
    """No downgrade — cannot distinguish formerly-ARCHIVED tasks from genuinely DELETED ones."""
    pass
