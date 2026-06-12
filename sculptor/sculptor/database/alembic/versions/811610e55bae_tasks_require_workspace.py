"""tasks require workspace

Revision ID: 811610e55bae
Revises: 9bb41574855c
Create Date: 2026-01-26 16:58:14.595401

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from sculptor.primitives.ids import ObjectSnapshotID
from sculptor.primitives.ids import WorkspaceID

# revision identifiers, used by Alembic.
revision: str = "811610e55bae"
down_revision: str | None = "9bb41574855c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    # Create workspace tables FIRST so we can insert data for existing tasks
    op.create_table(
        "workspace",
        sa.Column("snapshot_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("organization_reference", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("initialization_strategy", sa.String(), nullable=False),
        sa.Column("source_branch", sa.String(), nullable=True),
        sa.Column("environment_id", sa.String(), nullable=True),
        sa.Column("source_git_hash", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_deleted", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_table(
        "workspace_latest",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("organization_reference", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("initialization_strategy", sa.String(), nullable=False),
        sa.Column("source_branch", sa.String(), nullable=True),
        sa.Column("environment_id", sa.String(), nullable=True),
        sa.Column("source_git_hash", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_deleted", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project_latest.object_id"],
            name="foreign_key_workspace_project_id",
        ),
        sa.PrimaryKeyConstraint("object_id"),
    )

    # Find tasks that need workspace creation (AgentTaskStateV2 without workspace_id)
    result = connection.execute(
        sa.text("""
            SELECT
                object_id,
                organization_reference,
                project_id,
                json_extract(input_data, '$.git_hash') as git_hash,
                json_extract(current_state, '$.environment_id') as environment_id,
                json_extract(current_state, '$.title') as title,
                json_extract(current_state, '$.source_branch') as source_branch,
                json_extract(current_state, '$.mode') as mode
            FROM task_latest
            WHERE is_deleted = 0
            AND json_extract(current_state, '$.object_type') = 'AgentTaskStateV2'
            AND json_extract(current_state, '$.workspace_id') IS NULL
        """)
    )
    tasks_without_workspace = result.fetchall()

    # Create workspace for each task
    for row in tasks_without_workspace:
        task_id, org_ref, project_id, git_hash, environment_id, title, source_branch, mode = row

        # Generate IDs
        workspace_id = WorkspaceID()
        snapshot_id = ObjectSnapshotID()

        description = title or f"Workspace for task {task_id}"
        # Map task mode to workspace initialization_strategy (default to IN_PLACE)
        initialization_strategy = mode or "IN_PLACE"

        # Insert into workspace table (snapshots)
        connection.execute(
            sa.text("""
                INSERT INTO workspace (
                    snapshot_id, created_at, object_id, project_id, organization_reference,
                    description, initialization_strategy, source_branch, environment_id,
                    source_git_hash, status, is_deleted
                ) VALUES (
                    :snapshot_id, datetime('now'), :object_id, :project_id, :org_ref,
                    :description, :initialization_strategy, :source_branch, :environment_id,
                    :git_hash, 'ACTIVE', 0
                )
            """),
            {
                "snapshot_id": str(snapshot_id),
                "object_id": str(workspace_id),
                "project_id": project_id,
                "org_ref": org_ref,
                "description": description,
                "initialization_strategy": initialization_strategy,
                "source_branch": source_branch,
                "environment_id": environment_id,
                "git_hash": git_hash,
            },
        )

        # Insert into workspace_latest (triggers don't exist during migration)
        connection.execute(
            sa.text("""
                INSERT INTO workspace_latest (
                    created_at, object_id, project_id, organization_reference,
                    description, initialization_strategy, source_branch, environment_id,
                    source_git_hash, status, is_deleted
                ) VALUES (
                    datetime('now'), :object_id, :project_id, :org_ref,
                    :description, :initialization_strategy, :source_branch, :environment_id,
                    :git_hash, 'ACTIVE', 0
                )
            """),
            {
                "object_id": str(workspace_id),
                "project_id": project_id,
                "org_ref": org_ref,
                "description": description,
                "initialization_strategy": initialization_strategy,
                "source_branch": source_branch,
                "environment_id": environment_id,
                "git_hash": git_hash,
            },
        )

        # Update task_latest's current_state to add workspace_id
        connection.execute(
            sa.text("""
                UPDATE task_latest
                SET current_state = json_set(current_state, '$.workspace_id', :workspace_id)
                WHERE object_id = :task_id
            """),
            {"workspace_id": str(workspace_id), "task_id": task_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("workspace_latest")
    op.drop_table("workspace")
    # ### end Alembic commands ###
