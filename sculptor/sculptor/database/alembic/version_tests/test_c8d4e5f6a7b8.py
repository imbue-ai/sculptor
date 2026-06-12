import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-test-setup-backfill"
WS_UNTRIGGERED_ID = "ws-untriggered-setup"
WS_TRIGGERED_ID = "ws-triggered-setup"


class TestBackfillSetupCommandTriggered(MigrationTestFixture):
    """Test fixture for the migration that backfills setup_command_triggered=True."""

    @property
    def revision(self) -> str:
        return "c8d4e5f6a7b8"

    @property
    def down_revision(self) -> str:
        return "b9e29dc159f6"

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

        for ws_id, triggered, snap_suffix in (
            (WS_UNTRIGGERED_ID, 0, "untriggered"),
            (WS_TRIGGERED_ID, 1, "triggered"),
        ):
            for table in ("workspace", "workspace_latest"):
                snapshot_cols = "snapshot_id, " if table == "workspace" else ""
                snapshot_vals = f"'snap-{snap_suffix}', " if table == "workspace" else ""
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
                            :triggered, 1
                        )
                    """),
                    {"ws_id": ws_id, "project_id": PROJECT_ID, "triggered": triggered},
                )

    def verify(self, connection: sa.engine.Connection) -> None:
        for table in ("workspace", "workspace_latest"):
            for ws_id in (WS_UNTRIGGERED_ID, WS_TRIGGERED_ID):
                result = connection.execute(
                    sa.text(f"SELECT setup_command_triggered FROM {table} WHERE object_id = :ws_id"),
                    {"ws_id": ws_id},
                )
                row = result.fetchone()
                assert row is not None
                assert row[0] == 1, f"Expected setup_command_triggered=1 in {table} for {ws_id}, got {row[0]!r}"
