"""move system prompt to project

Revision ID: b777f4232d0b
Revises: be4a0386b97c
Create Date: 2025-09-25 15:40:55.781176

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b777f4232d0b"
down_revision: str | None = "be4a0386b97c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_user_settings_triggers() -> None:
    """Remove automanaged triggers so schema changes succeed."""

    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS user_settings_before_insert;")
        op.execute("DROP TRIGGER IF EXISTS set_user_settings_created_at;")
    elif dialect == "postgresql":
        op.execute('DROP TRIGGER IF EXISTS user_settings_before_insert ON "user_settings";')
        op.execute("DROP FUNCTION IF EXISTS refresh_user_settings_latest();")


def _backfill_project_prompts(connection) -> None:
    """Populate project defaults using the previous user-level default."""

    default_prompt = connection.execute(
        sa.text(
            """
            SELECT default_system_prompt
            FROM user_settings_latest
            WHERE default_system_prompt IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
    ).scalar()

    if default_prompt is None:
        return

    connection.execute(
        sa.text("UPDATE project_latest SET default_system_prompt = :prompt"),
        {"prompt": default_prompt},
    )
    connection.execute(
        sa.text("UPDATE project SET default_system_prompt = :prompt"),
        {"prompt": default_prompt},
    )


def upgrade() -> None:
    """Upgrade schema."""
    _drop_user_settings_triggers()

    with op.batch_alter_table("project", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("default_system_prompt", sa.String(), nullable=True))

    with op.batch_alter_table("project_latest", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("default_system_prompt", sa.String(), nullable=True))

    _backfill_project_prompts(op.get_bind())

    with op.batch_alter_table("user_settings", recreate="auto") as batch_op:
        batch_op.drop_column("default_system_prompt")

    with op.batch_alter_table("user_settings_latest", recreate="auto") as batch_op:
        batch_op.drop_column("default_system_prompt")


def downgrade() -> None:
    """Downgrade schema."""
    _drop_user_settings_triggers()

    with op.batch_alter_table("user_settings_latest", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("default_system_prompt", sa.VARCHAR(), nullable=True))

    with op.batch_alter_table("user_settings", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("default_system_prompt", sa.VARCHAR(), nullable=True))

    with op.batch_alter_table("project_latest", recreate="auto") as batch_op:
        batch_op.drop_column("default_system_prompt")

    with op.batch_alter_table("project", recreate="auto") as batch_op:
        batch_op.drop_column("default_system_prompt")
