"""Stop mirroring users and organizations.

Revision ID: 9b200ee9972c
Revises: 37411143b314
Create Date: 2025-08-18 13:39:02.189082

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# Duplicate these constants to make sure the migration script keeps working the same regardless of codebase changes.
ANONYMOUS_USER_REFERENCE = "777777777"
ANONYMOUS_ORGANIZATION_REFERENCE = "77777777-7777-7777-7777-777777777777"


# revision identifiers, used by Alembic.
revision: str = "9b200ee9972c"
down_revision: str | None = "f35851ffaae2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    # The necessary triggers will be recreated next time the application starts.
    op.execute("DROP TRIGGER IF EXISTS user_before_insert;")
    op.execute("DROP TRIGGER IF EXISTS set_user_created_at;")
    op.execute("DROP TRIGGER IF EXISTS organization_before_insert;")
    op.execute("DROP TRIGGER IF EXISTS set_organization_created_at;")
    op.execute("DROP TRIGGER IF EXISTS organization_membership_link_before_insert;")
    op.execute("DROP TRIGGER IF EXISTS set_organization_membership_link_created_at;")
    op.execute("DROP TRIGGER IF EXISTS project_before_insert;")
    op.execute("DROP TRIGGER IF EXISTS set_project_created_at;")
    op.execute("DROP TRIGGER IF EXISTS task_before_insert;")
    op.execute("DROP TRIGGER IF EXISTS set_task_created_at;")

    # Use temporary defaults during the migration.
    # We haven't really rolled out logins yet so it's fine to link all records to the anonymous user and organization.
    with op.batch_alter_table("project_latest") as batch_op:
        batch_op.drop_constraint("foreign_key_organization_id", type_="foreignkey")
        batch_op.drop_column("organization_id")
        batch_op.add_column(
            sa.Column(
                "organization_reference", sa.String(), nullable=False, server_default=ANONYMOUS_ORGANIZATION_REFERENCE
            )
        )
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("organization_id")
        batch_op.add_column(
            sa.Column(
                "organization_reference", sa.String(), nullable=False, server_default=ANONYMOUS_ORGANIZATION_REFERENCE
            )
        )

    with op.batch_alter_table("task_latest") as batch_op:
        batch_op.drop_constraint("foreign_key_organization_id", type_="foreignkey")
        batch_op.drop_constraint("foreign_key_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.drop_column("organization_id")
        batch_op.add_column(
            sa.Column(
                "organization_reference", sa.String(), nullable=False, server_default=ANONYMOUS_ORGANIZATION_REFERENCE
            )
        )
        batch_op.add_column(
            sa.Column("user_reference", sa.String(), nullable=False, server_default=ANONYMOUS_USER_REFERENCE),
        )

    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("user_id")
        batch_op.drop_column("organization_id")
        batch_op.add_column(
            sa.Column(
                "organization_reference", sa.String(), nullable=False, server_default=ANONYMOUS_ORGANIZATION_REFERENCE
            )
        )
        batch_op.add_column(
            sa.Column("user_reference", sa.String(), nullable=False, server_default=ANONYMOUS_USER_REFERENCE)
        )

    with op.batch_alter_table("notification") as batch_op:
        batch_op.drop_column("user_id")
        batch_op.add_column(
            sa.Column("user_reference", sa.String(), nullable=False, server_default=ANONYMOUS_USER_REFERENCE),
        )

    op.drop_table("organization_membership_link_latest")
    op.drop_table("organization_membership_link")

    op.drop_table("organization")
    op.drop_table("organization_latest")

    op.rename_table("user", "user_settings")
    op.rename_table("user_latest", "user_settings_latest")

    with op.batch_alter_table("user_settings_latest") as batch_op:
        batch_op.drop_column("authentik_id")
        batch_op.drop_column("email")
        batch_op.add_column(
            sa.Column("user_reference", sa.String(), nullable=False, server_default=ANONYMOUS_USER_REFERENCE)
        )
        batch_op.create_unique_constraint("unique_user_reference", ["user_reference"])

    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("authentik_id")
        batch_op.drop_column("email")
        batch_op.add_column(
            sa.Column("user_reference", sa.String(), nullable=False, server_default=ANONYMOUS_USER_REFERENCE),
        )

    # Remove the temporary defaults.
    with op.batch_alter_table("project_latest") as batch_op:
        batch_op.alter_column("organization_reference", server_default=None)
    with op.batch_alter_table("project") as batch_op:
        batch_op.alter_column("organization_reference", server_default=None)
    with op.batch_alter_table("task_latest") as batch_op:
        batch_op.alter_column("organization_reference", server_default=None)
        batch_op.alter_column("user_reference", server_default=None)
    with op.batch_alter_table("task") as batch_op:
        batch_op.alter_column("organization_reference", server_default=None)
        batch_op.alter_column("user_reference", server_default=None)
    with op.batch_alter_table("notification") as batch_op:
        batch_op.alter_column("user_reference", server_default=None)
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.alter_column("user_reference", server_default=None)
    with op.batch_alter_table("user_settings_latest") as batch_op:
        batch_op.alter_column("user_reference", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError()
