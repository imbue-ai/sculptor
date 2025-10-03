"""remove unused messages

Revision ID: 8a4050464872
Revises: 9b200ee9972c
Create Date: 2025-08-19 13:23:57.250301

"""

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a4050464872"
down_revision: str | None = "9b200ee9972c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use json_extract for SQLite (which is what we're using)
    op.execute("""
        DELETE FROM saved_agent_message
        WHERE json_extract(message, '$.object_type') = 'CompletedResponseAgentMessage'
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
