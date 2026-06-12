import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-target-branch"
WS_NULL_ID = "ws-null-target"
WS_EMPTY_ID = "ws-empty-target"
WS_SET_ID = "ws-set-target"


class TestBackfillTargetBranchDefault(MigrationTestFixture):
    """Test fixture for the migration that backfills target_branch with 'origin/main'."""

    @property
    def revision(self) -> str:
        return "bcc42be33ebc"

    @property
    def down_revision(self) -> str:
        return "eedceaef0697"

    def seed(self, connection: sa.engine.Connection) -> None:
        # Insert a project
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

        # Workspace with NULL target_branch
        for table in ("workspace", "workspace_latest"):
            snapshot_cols = "snapshot_id, " if table == "workspace" else ""
            snapshot_vals = "'snap-null', " if table == "workspace" else ""
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table} (
                        {snapshot_cols}created_at, object_id, project_id, organization_reference,
                        description, initialization_strategy, source_branch,
                        source_git_hash, is_deleted, diff_status, target_branch
                    ) VALUES (
                        {snapshot_vals}'2026-01-01T00:00:00', :ws_id, :project_id, 'org-1',
                        'null workspace', 'CLONE', NULL,
                        'abc123', 0, 'NONE', NULL
                    )
                """),
                {"ws_id": WS_NULL_ID, "project_id": PROJECT_ID},
            )

        # Workspace with empty string target_branch
        for table in ("workspace", "workspace_latest"):
            snapshot_cols = "snapshot_id, " if table == "workspace" else ""
            snapshot_vals = "'snap-empty', " if table == "workspace" else ""
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table} (
                        {snapshot_cols}created_at, object_id, project_id, organization_reference,
                        description, initialization_strategy, source_branch,
                        source_git_hash, is_deleted, diff_status, target_branch
                    ) VALUES (
                        {snapshot_vals}'2026-01-01T00:00:00', :ws_id, :project_id, 'org-1',
                        'empty workspace', 'CLONE', NULL,
                        'def456', 0, 'NONE', ''
                    )
                """),
                {"ws_id": WS_EMPTY_ID, "project_id": PROJECT_ID},
            )

        # Workspace with an already-set target_branch (should not be changed)
        for table in ("workspace", "workspace_latest"):
            snapshot_cols = "snapshot_id, " if table == "workspace" else ""
            snapshot_vals = "'snap-set', " if table == "workspace" else ""
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table} (
                        {snapshot_cols}created_at, object_id, project_id, organization_reference,
                        description, initialization_strategy, source_branch,
                        source_git_hash, is_deleted, diff_status, target_branch
                    ) VALUES (
                        {snapshot_vals}'2026-01-01T00:00:00', :ws_id, :project_id, 'org-1',
                        'set workspace', 'CLONE', NULL,
                        'ghi789', 0, 'NONE', 'origin/develop'
                    )
                """),
                {"ws_id": WS_SET_ID, "project_id": PROJECT_ID},
            )

    def verify(self, connection: sa.engine.Connection) -> None:
        for table in ("workspace", "workspace_latest"):
            # NULL target_branch should now be 'origin/main'
            result = connection.execute(
                sa.text(f"SELECT target_branch FROM {table} WHERE object_id = :ws_id"),
                {"ws_id": WS_NULL_ID},
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "origin/main", f"Expected 'origin/main' for NULL workspace in {table}, got {row[0]!r}"

            # Empty target_branch should now be 'origin/main'
            result = connection.execute(
                sa.text(f"SELECT target_branch FROM {table} WHERE object_id = :ws_id"),
                {"ws_id": WS_EMPTY_ID},
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "origin/main", f"Expected 'origin/main' for empty workspace in {table}, got {row[0]!r}"

            # Already-set target_branch should be unchanged
            result = connection.execute(
                sa.text(f"SELECT target_branch FROM {table} WHERE object_id = :ws_id"),
                {"ws_id": WS_SET_ID},
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "origin/develop", (
                f"Expected 'origin/develop' for set workspace in {table}, got {row[0]!r}"
            )
