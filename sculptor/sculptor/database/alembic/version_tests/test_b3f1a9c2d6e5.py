import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-harness-drop"
WORKSPACE_ID = "ws-test-harness-drop"


class TestMigrationB3f1a9c2d6e5(MigrationTestFixture):
    """Dropping the harness column preserves workspace rows (including pi ones).

    Agent type lives on each task's agent_config, so no per-row data needs
    migrating — the column simply disappears.
    """

    @property
    def revision(self) -> str:
        return "b3f1a9c2d6e5"

    @property
    def down_revision(self) -> str:
        return "587b6b6e8747"

    def seed(self, connection: sa.engine.Connection) -> None:
        connection.execute(
            sa.text("""
                INSERT INTO project_latest (
                    created_at, object_id, organization_reference,
                    name, user_git_repo_url, is_path_accessible,
                    is_deleted, default_system_prompt
                ) VALUES (
                    '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', NULL, 1, 0, NULL
                )
            """),
            {"project_id": PROJECT_ID},
        )

        for table in ("workspace", "workspace_latest"):
            snapshot_cols = "snapshot_id, " if table == "workspace" else ""
            snapshot_vals = "'snap-harness-drop', " if table == "workspace" else ""
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table} (
                        {snapshot_cols}created_at, object_id, project_id, organization_reference,
                        description, initialization_strategy, source_branch,
                        source_git_hash, is_deleted, diff_status, target_branch,
                        setup_command_triggered, is_open, harness
                    ) VALUES (
                        {snapshot_vals}'2026-01-01T00:00:00', :ws_id, :project_id, 'org-1',
                        'workspace', 'CLONE', NULL,
                        'abc123', 0, 'NONE', 'origin/main',
                        0, 1, 'pi'
                    )
                """),
                {"ws_id": WORKSPACE_ID, "project_id": PROJECT_ID},
            )

    def verify(self, connection: sa.engine.Connection) -> None:
        for table in ("workspace", "workspace_latest"):
            columns = {
                row[1]
                for row in connection.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()  # noqa: S608
            }
            assert "harness" not in columns, f"Expected harness column to be dropped from {table}"

            result = connection.execute(
                sa.text(f"SELECT description FROM {table} WHERE object_id = :ws_id"),
                {"ws_id": WORKSPACE_ID},
            )
            row = result.fetchone()
            assert row is not None, f"Expected row in {table} for {WORKSPACE_ID} to survive the drop"
            assert row[0] == "workspace"
