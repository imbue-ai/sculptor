"""drop product-logging / usage-data columns

Removes the abandoned product-logging / usage-data consent feature columns,
which have no production readers:

  * ``user_settings`` / ``user_settings_latest``: ``is_usage_data_enabled``,
    ``allowed_product_logging``
  * ``project`` / ``project_latest``: ``is_loggable``
  * ``notification``: ``url`` (``notification`` has no ``_latest`` shadow)

Revision ID: 6ab148aeec31
Revises: f332049181c5
Create Date: 2026-05-30 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ab148aeec31"
down_revision: str | None = "f332049181c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    # Drop the auto-managed triggers that reference the to-be-dropped columns
    # before dropping those columns. SQLite validates trigger bodies during
    # ALTER TABLE ... DROP COLUMN, so a trigger that references a removed column
    # (e.g. user_settings_before_insert -> excluded.allowed_product_logging,
    # project_before_insert -> excluded.is_loggable) would otherwise abort the
    # migration on any pre-existing database that already has the triggers
    # installed. The triggers are recreated by initialize_db() on the next
    # Sculptor startup. (notification is a non-dual table, so it has no triggers.)
    connection.execute(sa.text("DROP TRIGGER IF EXISTS user_settings_before_insert"))
    connection.execute(sa.text("DROP TRIGGER IF EXISTS set_user_settings_created_at"))
    connection.execute(sa.text("DROP TRIGGER IF EXISTS project_before_insert"))
    connection.execute(sa.text("DROP TRIGGER IF EXISTS set_project_created_at"))

    op.drop_column("user_settings_latest", "allowed_product_logging")
    op.drop_column("user_settings_latest", "is_usage_data_enabled")
    op.drop_column("user_settings", "allowed_product_logging")
    op.drop_column("user_settings", "is_usage_data_enabled")
    op.drop_column("project_latest", "is_loggable")
    op.drop_column("project", "is_loggable")
    op.drop_column("notification", "url")


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add the columns with their original types/nullability. The not-null
    # columns get a server_default so the re-add succeeds against populated
    # tables (the initial migration created them on empty tables).
    op.add_column("notification", sa.Column("url", sa.String(), nullable=True))
    op.add_column("project", sa.Column("is_loggable", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("project_latest", sa.Column("is_loggable", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "user_settings",
        sa.Column("is_usage_data_enabled", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_settings",
        sa.Column("allowed_product_logging", sa.String(), nullable=False, server_default="NONE"),
    )
    op.add_column(
        "user_settings_latest",
        sa.Column("is_usage_data_enabled", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_settings_latest",
        sa.Column("allowed_product_logging", sa.String(), nullable=False, server_default="NONE"),
    )
