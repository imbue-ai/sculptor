import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-1"
WORKSPACE_ID = "ws-test-1"


class TestMigration0fb6dc48c8ef(MigrationTestFixture):
    """Test that adding target_branch to workspace preserves existing data."""

    @property
    def revision(self) -> str:
        return "0fb6dc48c8ef"

    @property
    def down_revision(self) -> str:
        return "865d3a5b4f84"

    def seed(self, connection: sa.engine.Connection) -> None:
        connection.execute(
            sa.text("""
                INSERT INTO project_latest (
                    created_at, object_id, organization_reference,
                    name, user_git_repo_url, is_loggable, is_path_accessible,
                    is_deleted, default_system_prompt
                ) VALUES (
                    '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', NULL, 1, 1, 0, NULL
                )
            """),
            {"project_id": PROJECT_ID},
        )

        connection.execute(
            sa.text("""
                INSERT INTO workspace (
                    snapshot_id, created_at, object_id, project_id,
                    organization_reference, description, initialization_strategy,
                    source_branch, environment_id, source_git_hash,
                    diff_status, diff_updated_at, is_deleted
                ) VALUES (
                    'snap-ws-1', '2026-01-01T00:00:00', :workspace_id, :project_id,
                    'org-1', 'Test Workspace', 'IN_PLACE',
                    'main', 'env-1', 'abc123',
                    'CLEAN', NULL, 0
                )
            """),
            {"workspace_id": WORKSPACE_ID, "project_id": PROJECT_ID},
        )
        connection.execute(
            sa.text("""
                INSERT INTO workspace_latest (
                    created_at, object_id, project_id,
                    organization_reference, description, initialization_strategy,
                    source_branch, environment_id, source_git_hash,
                    diff_status, diff_updated_at, is_deleted
                ) VALUES (
                    '2026-01-01T00:00:00', :workspace_id, :project_id,
                    'org-1', 'Test Workspace', 'IN_PLACE',
                    'main', 'env-1', 'abc123',
                    'CLEAN', NULL, 0
                )
            """),
            {"workspace_id": WORKSPACE_ID, "project_id": PROJECT_ID},
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Check target_branch column exists on both tables
        workspace_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(workspace)"))}
        assert "target_branch" in workspace_columns, "target_branch column missing from workspace"

        workspace_latest_columns = {
            row[1] for row in connection.execute(sa.text("PRAGMA table_info(workspace_latest)"))
        }
        assert "target_branch" in workspace_latest_columns, "target_branch column missing from workspace_latest"

        # Check existing workspace data is preserved with target_branch defaulting to NULL
        result = connection.execute(
            sa.text("""
                SELECT object_id, description, source_branch, target_branch
                FROM workspace
                WHERE object_id = :workspace_id
            """),
            {"workspace_id": WORKSPACE_ID},
        )
        row = result.fetchone()
        assert row is not None, "Workspace not found after migration"
        assert row[0] == WORKSPACE_ID
        assert row[1] == "Test Workspace"
        assert row[2] == "main"
        assert row[3] is None, f"Expected target_branch to be NULL, got {row[3]}"
