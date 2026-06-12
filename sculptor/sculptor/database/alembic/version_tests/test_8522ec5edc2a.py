import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

WORKSPACE_ID = "ws-test-1"


class TestDropWorkspaceStatusColumn(MigrationTestFixture):
    """Test fixture for the migration that drops the status column from workspace tables."""

    @property
    def revision(self) -> str:
        return "8522ec5edc2a"

    @property
    def down_revision(self) -> str:
        return "20fea77a3f5a"

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

        # Insert a workspace with both status and diff_status columns
        # (at this point the schema has both columns)
        connection.execute(
            sa.text("""
                INSERT INTO workspace (
                    snapshot_id, created_at, object_id, project_id,
                    organization_reference, description, initialization_strategy,
                    source_branch, environment_id, source_git_hash,
                    status, diff_status, diff_updated_at, is_deleted
                ) VALUES (
                    'snap-ws-1', '2026-01-01T00:00:00', :workspace_id, 'proj-test-1',
                    'org-1', 'Test Workspace', 'IN_PLACE',
                    'main', 'env-1', 'abc123',
                    'ACTIVE', 'CLEAN', NULL, 0
                )
            """),
            {"workspace_id": WORKSPACE_ID},
        )
        connection.execute(
            sa.text("""
                INSERT INTO workspace_latest (
                    created_at, object_id, project_id,
                    organization_reference, description, initialization_strategy,
                    source_branch, environment_id, source_git_hash,
                    status, diff_status, diff_updated_at, is_deleted
                ) VALUES (
                    '2026-01-01T00:00:00', :workspace_id, 'proj-test-1',
                    'org-1', 'Test Workspace', 'IN_PLACE',
                    'main', 'env-1', 'abc123',
                    'ACTIVE', 'CLEAN', NULL, 0
                )
            """),
            {"workspace_id": WORKSPACE_ID},
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # Check status column no longer exists on workspace
        workspace_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(workspace)"))}
        assert "status" not in workspace_columns, "status column still in workspace table"

        # Check status column no longer exists on workspace_latest
        workspace_latest_columns = {
            row[1] for row in connection.execute(sa.text("PRAGMA table_info(workspace_latest)"))
        }
        assert "status" not in workspace_latest_columns, "status column still in workspace_latest table"

        # Check other workspace data is preserved
        result = connection.execute(
            sa.text("""
                SELECT object_id, description, diff_status, initialization_strategy
                FROM workspace
                WHERE object_id = :workspace_id
            """),
            {"workspace_id": WORKSPACE_ID},
        )
        row = result.fetchone()
        assert row is not None, "Workspace data not preserved after migration"
        assert row[0] == WORKSPACE_ID
        assert row[1] == "Test Workspace"
        assert row[2] == "CLEAN"
        assert row[3] == "IN_PLACE"
