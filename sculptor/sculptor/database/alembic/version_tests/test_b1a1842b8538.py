import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-workspace-groups"
WORKSPACE_ID = "ws-workspace-groups"

EXPECTED_GROUP_COLUMNS = {
    "snapshot_id",
    "created_at",
    "object_id",
    "organization_reference",
    "project_id",
    "name",
    "color",
    "created_via_cli",
    "is_deleted",
}


class TestMigrationB1a1842b8538(MigrationTestFixture):
    """The workspace group tables appear and existing workspaces backfill to no group.

    Group membership is newly persisted on the workspace; a pre-existing row
    must come out of the migration loose (group_id NULL).
    """

    @property
    def revision(self) -> str:
        return "b1a1842b8538"

    @property
    def down_revision(self) -> str:
        return "5cb094ae1d22"

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
            snapshot_vals = "'snap-workspace-groups', " if table == "workspace" else ""
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table} (
                        {snapshot_cols}created_at, object_id, project_id, organization_reference,
                        description, initialization_strategy, source_branch,
                        source_git_hash, is_deleted, diff_status, target_branch,
                        setup_command_triggered, is_open
                    ) VALUES (
                        {snapshot_vals}'2026-01-01T00:00:00', :ws_id, :project_id, 'org-1',
                        'workspace', 'CLONE', NULL,
                        'abc123', 0, 'NONE', 'origin/main',
                        0, 1
                    )
                """),  # noqa: S608
                {"ws_id": WORKSPACE_ID, "project_id": PROJECT_ID},
            )

    def verify(self, connection: sa.engine.Connection) -> None:
        for table in ("workspace_group", "workspace_group_latest"):
            columns = {
                row[1]
                for row in connection.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()  # noqa: S608
            }
            expected = (
                EXPECTED_GROUP_COLUMNS if table == "workspace_group" else EXPECTED_GROUP_COLUMNS - {"snapshot_id"}
            )
            assert columns == expected, f"Unexpected columns on {table}: {sorted(columns)}"

        for table in ("workspace", "workspace_latest"):
            columns = {
                row[1]
                for row in connection.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()  # noqa: S608
            }
            assert "group_id" in columns, f"Expected group_id column on {table}"

            result = connection.execute(
                sa.text(f"SELECT group_id FROM {table} WHERE object_id = :ws_id"),  # noqa: S608
                {"ws_id": WORKSPACE_ID},
            )
            row = result.fetchone()
            assert row is not None, f"Expected row in {table} for {WORKSPACE_ID} to survive the migration"
            assert row[0] is None, f"Expected pre-existing workspace to backfill to no group, got {row[0]}"
