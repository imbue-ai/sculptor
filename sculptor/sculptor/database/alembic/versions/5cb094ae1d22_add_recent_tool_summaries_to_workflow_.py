"""add recent_tool_summaries to WorkflowAgentProgress

No SQL changes are needed — the new field lives inside JSON blobs (nested
in BackgroundTaskNotificationAgentMessage.final_workflow_entries) and
defaults to an empty tuple, so existing data is unaffected.

Revision ID: 5cb094ae1d22
Revises: 4a289e39dd87
Create Date: 2026-07-02 12:57:49.717321

"""

from typing import Sequence

# revision identifiers, used by Alembic.
revision: str = "5cb094ae1d22"
down_revision: str | None = "4a289e39dd87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
