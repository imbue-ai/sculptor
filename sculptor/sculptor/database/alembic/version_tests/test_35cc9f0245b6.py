import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_WITH_CMD_ID = "proj-with-setup-cmd"
PROJECT_NO_CMD_ID = "proj-no-setup-cmd"
PROJECT_EMPTY_CMD_ID = "proj-empty-setup-cmd"

WS_TRIGGERED_ID = "ws-triggered"
# A workspace whose legacy `setup_command_triggered=0` while the project has a
# command configured. Pre-fix the migration auto-promoted this to "pending" and
# the runner would auto-fire setup on the next open. Post-fix it must land in
# "not_configured" — the user manually opts in via the Run-setup button.
WS_NEVER_RAN_WITH_PROJECT_CMD_ID = "ws-never-ran-with-project-cmd"
WS_NO_CMD_ID = "ws-no-cmd"
WS_EMPTY_CMD_ID = "ws-empty-cmd"


class TestBackfillSetupState(MigrationTestFixture):
    """Test fixture for the migration that backfills setup_status from
    the legacy setup_command_triggered flag and project workspace_setup_command.
    """

    @property
    def revision(self) -> str:
        return "35cc9f0245b6"

    @property
    def down_revision(self) -> str:
        return "b5a4106e6118"

    def seed(self, connection: sa.engine.Connection) -> None:
        for project_id, cmd in (
            (PROJECT_WITH_CMD_ID, "echo hi"),
            (PROJECT_NO_CMD_ID, None),
            (PROJECT_EMPTY_CMD_ID, ""),
        ):
            connection.execute(
                sa.text("""
                    INSERT INTO project_latest (
                        created_at, object_id, organization_reference,
                        name, user_git_repo_url, is_loggable, is_path_accessible,
                        is_deleted, default_system_prompt, workspace_setup_command
                    ) VALUES (
                        '2026-01-01T00:00:00', :project_id, 'org-1',
                        'Test Project', NULL, 1, 1, 0, NULL, :cmd
                    )
                """),
                {"project_id": project_id, "cmd": cmd},
            )
            connection.execute(
                sa.text("""
                    INSERT INTO project (
                        snapshot_id, created_at, object_id, organization_reference,
                        name, user_git_repo_url, is_loggable, is_path_accessible,
                        is_deleted, default_system_prompt, workspace_setup_command
                    ) VALUES (
                        :snap_id, '2026-01-01T00:00:00', :project_id, 'org-1',
                        'Test Project', NULL, 1, 1, 0, NULL, :cmd
                    )
                """),
                {"snap_id": f"snap-{project_id}", "project_id": project_id, "cmd": cmd},
            )

        for ws_id, project_id, triggered, snap_suffix in (
            (WS_TRIGGERED_ID, PROJECT_WITH_CMD_ID, 1, "triggered"),
            (WS_NEVER_RAN_WITH_PROJECT_CMD_ID, PROJECT_WITH_CMD_ID, 0, "never-ran-with-project-cmd"),
            (WS_NO_CMD_ID, PROJECT_NO_CMD_ID, 0, "no-cmd"),
            (WS_EMPTY_CMD_ID, PROJECT_EMPTY_CMD_ID, 0, "empty-cmd"),
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
                    {"ws_id": ws_id, "project_id": project_id, "triggered": triggered},
                )

    def verify(self, connection: sa.engine.Connection) -> None:
        expected = {
            WS_TRIGGERED_ID: "succeeded",
            # Pre-existing workspace that never ran setup must NOT be auto-promoted
            # to "pending" just because the project now has a command — that would
            # auto-fire the runner on next open.
            WS_NEVER_RAN_WITH_PROJECT_CMD_ID: "not_configured",
            WS_NO_CMD_ID: "not_configured",
            WS_EMPTY_CMD_ID: "not_configured",
        }
        for table in ("workspace", "workspace_latest"):
            for ws_id, expected_status in expected.items():
                result = connection.execute(
                    sa.text(f"SELECT setup_status FROM {table} WHERE object_id = :ws_id"),
                    {"ws_id": ws_id},
                )
                row = result.fetchone()
                assert row is not None, f"Missing row for {ws_id} in {table}"
                assert row[0] == expected_status, (
                    f"Expected setup_status={expected_status!r} in {table} for {ws_id}, got {row[0]!r}"
                )
