import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

_PROJECT_ID = "proj-test-use-jj-for-new-workspaces"


class TestMigration66b62ccf5ff4(MigrationTestFixture):
    """Existing projects keep making git workspaces: the new flag reads as off."""

    @property
    def revision(self) -> str:
        return "66b62ccf5ff4"

    @property
    def down_revision(self) -> str:
        return "6026c03dc852"

    def seed(self, connection: sa.engine.Connection) -> None:
        for table in ("project", "project_latest"):
            snapshot_column = "snapshot_id, " if table == "project" else ""
            snapshot_value = "'snap-use-jj', " if table == "project" else ""
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table} (
                        {snapshot_column}created_at, object_id, organization_reference,
                        name, user_git_repo_url, is_path_accessible, is_deleted
                    ) VALUES (
                        {snapshot_value}'2026-01-01T00:00:00', :project_id, 'org-1',
                        'Test Project', NULL, 1, 0
                    )
                """),
                {"project_id": _PROJECT_ID},
            )

    def verify(self, connection: sa.engine.Connection) -> None:
        for table in ("project", "project_latest"):
            row = connection.execute(
                sa.text(f"SELECT use_jj_for_new_workspaces FROM {table} WHERE object_id = :project_id"),
                {"project_id": _PROJECT_ID},
            ).fetchone()
            assert row is not None
            assert row[0] == 0, f"Expected use_jj_for_new_workspaces=0 in {table}, got {row[0]!r}"
