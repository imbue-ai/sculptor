import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

WORKSPACE_ID = "ws-test-1"


class TestAddDiffStatusAndDiffUpdatedAt(MigrationTestFixture):
    """Test fixture for the migration that adds diff_status and diff_updated_at to workspace."""

    @property
    def revision(self) -> str:
        return "20fea77a3f5a"

    @property
    def down_revision(self) -> str:
        return "ad24ef11df19"

    def seed(self, connection: sa.engine.Connection) -> None:
        # Insert a project (needed for workspace FK)
        connection.execute(
            sa.text("""
                INSERT INTO project_latest (
                    created_at, object_id, organization_reference,
                    name, user_git_repo_url, is_loggable, is_path_accessible,
                    is_deleted, default_system_prompt
                ) VALUES (
                    '2026-01-01T00:00:00', 'proj-test-1', 'org-1',
                    'Test Project', NULL, 1, 1, 0, NULL
                )
            """)
        )

        # Insert a workspace row (schema at this point has status but not diff_status)
        connection.execute(
            sa.text("""
                INSERT INTO workspace (
                    snapshot_id, created_at, object_id, project_id,
                    organization_reference, description, initialization_strategy,
                    source_branch, environment_id, source_git_hash, status, is_deleted
                ) VALUES (
                    'snap-ws-1', '2026-01-01T00:00:00', :workspace_id, 'proj-test-1',
                    'org-1', 'Test Workspace', 'IN_PLACE',
                    'main', 'env-1', 'abc123', 'ACTIVE', 0
                )
            """),
            {"workspace_id": WORKSPACE_ID},
        )
        connection.execute(
            sa.text("""
                INSERT INTO workspace_latest (
                    created_at, object_id, project_id,
                    organization_reference, description, initialization_strategy,
                    source_branch, environment_id, source_git_hash, status, is_deleted
                ) VALUES (
                    '2026-01-01T00:00:00', :workspace_id, 'proj-test-1',
                    'org-1', 'Test Workspace', 'IN_PLACE',
                    'main', 'env-1', 'abc123', 'ACTIVE', 0
                )
            """),
            {"workspace_id": WORKSPACE_ID},
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Check diff_status and diff_updated_at columns exist on workspace
        workspace_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(workspace)"))}
        assert "diff_status" in workspace_columns, "diff_status column not found in workspace"
        assert "diff_updated_at" in workspace_columns, "diff_updated_at column not found in workspace"

        # Check diff_status and diff_updated_at columns exist on workspace_latest
        workspace_latest_columns = {
            row[1] for row in connection.execute(sa.text("PRAGMA table_info(workspace_latest)"))
        }
        assert "diff_status" in workspace_latest_columns, "diff_status column not found in workspace_latest"
        assert "diff_updated_at" in workspace_latest_columns, "diff_updated_at column not found in workspace_latest"

        # Check existing workspace has diff_status = 'NONE'
        result = connection.execute(
            sa.text("SELECT diff_status FROM workspace WHERE object_id = :workspace_id"),
            {"workspace_id": WORKSPACE_ID},
        )
        row = result.fetchone()
        assert row is not None, "Workspace not found after migration"
        assert row[0] == "NONE", f"Expected diff_status 'NONE', got '{row[0]}'"
