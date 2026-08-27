"""add workflow fields to BackgroundTaskNotificationAgentMessage

No SQL changes are needed — the new fields (workflow_name,
final_workflow_entries, workflow_usage, and the nested
WorkflowAgentProgress.recent_tool_summaries) live inside JSON blobs and
all default to empty/None, so existing data is unaffected.

Revision ID: 5cb094ae1d22
Revises: 34fe61b617e6
Create Date: 2026-07-02 09:52:21.412777

"""

from typing import Sequence

# revision identifiers, used by Alembic.
revision: str = "5cb094ae1d22"
down_revision: str | None = "34fe61b617e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
