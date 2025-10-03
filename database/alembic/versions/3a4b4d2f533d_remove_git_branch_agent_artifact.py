"""remove git branch agent artifact

Revision ID: 3a4b4d2f533d
Revises: e6789637fc58
Create Date: 2025-09-02 15:56:44.776037

"""

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a4b4d2f533d"
down_revision: str | None = "e6789637fc58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Get the database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # Delete UpdatedArtifactAgentMessages that contain GitBranchAgentArtifact
    if dialect_name == "postgresql":
        # PostgreSQL uses ->> for JSON text extraction
        op.execute("""
            DELETE FROM saved_agent_message
            WHERE message->>'object_type' = 'UpdatedArtifactAgentMessage'
            AND message->'artifact'->>'object_type' = 'GitBranchAgentArtifact'
        """)
    else:
        # SQLite uses json_extract
        op.execute("""
            DELETE FROM saved_agent_message
            WHERE json_extract(message, '$.object_type') = 'UpdatedArtifactAgentMessage'
            AND json_extract(message, '$.artifact.object_type') = 'GitBranchAgentArtifact'
        """)


def downgrade() -> None:
    """Downgrade schema."""
    # no downgrade necessary
    pass
