import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

PROJECT_ID = "proj-drop-logging-1"
USER_SETTINGS_ID = "user-settings-drop-logging-1"
USER_REFERENCE = "user-drop-logging-1"
NOTIFICATION_ID = "notif-drop-logging-1"


class TestDropProductLoggingColumns(MigrationTestFixture):
    """Test fixture for the migration that drops the abandoned product-logging /
    usage-data columns from the user_settings, project, and notification tables.
    """

    @property
    def revision(self) -> str:
        return "6ab148aeec31"

    @property
    def down_revision(self) -> str:
        return "f332049181c5"

    def seed(self, connection: sa.engine.Connection) -> None:
        # project + project_latest carry the to-be-dropped is_loggable column.
        connection.execute(
            sa.text("""
                INSERT INTO project_latest (
                    created_at, object_id, organization_reference,
                    name, is_loggable, is_path_accessible, is_deleted
                ) VALUES (
                    '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', 1, 1, 0
                )
            """),
            {"project_id": PROJECT_ID},
        )
        connection.execute(
            sa.text("""
                INSERT INTO project (
                    snapshot_id, created_at, object_id, organization_reference,
                    name, is_loggable, is_path_accessible, is_deleted
                ) VALUES (
                    'snap-proj-1', '2026-01-01T00:00:00', :project_id, 'org-1',
                    'Test Project', 1, 1, 0
                )
            """),
            {"project_id": PROJECT_ID},
        )

        # user_settings + user_settings_latest carry is_usage_data_enabled and
        # allowed_product_logging.
        connection.execute(
            sa.text("""
                INSERT INTO user_settings_latest (
                    created_at, object_id, user_reference,
                    is_usage_data_enabled, allowed_product_logging
                ) VALUES (
                    '2026-01-01T00:00:00', :object_id, :user_reference,
                    1, 'OPEN_SOURCE'
                )
            """),
            {"object_id": USER_SETTINGS_ID, "user_reference": USER_REFERENCE},
        )
        connection.execute(
            sa.text("""
                INSERT INTO user_settings (
                    snapshot_id, created_at, object_id, user_reference,
                    is_usage_data_enabled, allowed_product_logging
                ) VALUES (
                    'snap-settings-1', '2026-01-01T00:00:00', :object_id, :user_reference,
                    1, 'OPEN_SOURCE'
                )
            """),
            {"object_id": USER_SETTINGS_ID, "user_reference": USER_REFERENCE},
        )

        # notification carries the nullable url column (no _latest shadow table).
        connection.execute(
            sa.text("""
                INSERT INTO notification (
                    snapshot_id, created_at, object_id, user_reference,
                    message, importance, url
                ) VALUES (
                    'snap-notif-1', '2026-01-01T00:00:00', :object_id, :user_reference,
                    'Test notification', 'ACTIVE', 'https://example.com'
                )
            """),
            {"object_id": NOTIFICATION_ID, "user_reference": USER_REFERENCE},
        )

        # Install the auto-managed triggers that a real, pre-existing dev database
        # already has (initialize_db() creates them on every startup). Their bodies
        # reference the columns this migration drops, so SQLite's DROP COLUMN
        # validation aborts the migration unless it drops these triggers first.
        # Without this, the harness runs the migration against a trigger-free schema
        # and the bug goes undetected. Created last so they do not fire on the seed
        # inserts above.
        self._create_legacy_triggers(connection)

    @staticmethod
    def _create_legacy_triggers(connection: sa.engine.Connection) -> None:
        # Mirrors the pre-cleanup output of database/automanaged.py: a BEFORE INSERT
        # trigger that upserts into the _latest table (referencing the dropped
        # columns via excluded.*), plus the AFTER INSERT created_at trigger.
        connection.execute(
            sa.text("""
                CREATE TRIGGER user_settings_before_insert
                BEFORE INSERT ON user_settings
                BEGIN
                    INSERT INTO user_settings_latest (
                        object_id, user_reference, is_usage_data_enabled, allowed_product_logging, created_at
                    ) VALUES (
                        NEW.object_id, NEW.user_reference, NEW.is_usage_data_enabled,
                        NEW.allowed_product_logging, NEW.created_at
                    )
                    ON CONFLICT (object_id) DO UPDATE SET
                        user_reference = excluded.user_reference,
                        is_usage_data_enabled = excluded.is_usage_data_enabled,
                        allowed_product_logging = excluded.allowed_product_logging;
                END;
            """)
        )
        connection.execute(
            sa.text("""
                CREATE TRIGGER set_user_settings_created_at
                AFTER INSERT ON user_settings
                FOR EACH ROW
                BEGIN
                    UPDATE user_settings SET created_at = datetime('now') WHERE snapshot_id = NEW.snapshot_id;
                END;
            """)
        )
        connection.execute(
            sa.text("""
                CREATE TRIGGER project_before_insert
                BEFORE INSERT ON project
                BEGIN
                    INSERT INTO project_latest (
                        object_id, organization_reference, name, is_loggable,
                        is_path_accessible, is_deleted, created_at
                    ) VALUES (
                        NEW.object_id, NEW.organization_reference, NEW.name, NEW.is_loggable,
                        NEW.is_path_accessible, NEW.is_deleted, NEW.created_at
                    )
                    ON CONFLICT (object_id) DO UPDATE SET
                        organization_reference = excluded.organization_reference,
                        name = excluded.name,
                        is_loggable = excluded.is_loggable,
                        is_path_accessible = excluded.is_path_accessible,
                        is_deleted = excluded.is_deleted;
                END;
            """)
        )
        connection.execute(
            sa.text("""
                CREATE TRIGGER set_project_created_at
                AFTER INSERT ON project
                FOR EACH ROW
                BEGIN
                    UPDATE project SET created_at = datetime('now') WHERE snapshot_id = NEW.snapshot_id;
                END;
            """)
        )

    def verify(self, connection: sa.engine.Connection) -> None:
        # The dropped columns must be gone from every affected table.
        for table in ("project", "project_latest"):
            columns = {row[1] for row in connection.execute(sa.text(f"PRAGMA table_info({table})"))}
            assert "is_loggable" not in columns, f"is_loggable column still exists in {table}"

        for table in ("user_settings", "user_settings_latest"):
            columns = {row[1] for row in connection.execute(sa.text(f"PRAGMA table_info({table})"))}
            assert "is_usage_data_enabled" not in columns, f"is_usage_data_enabled column still exists in {table}"
            assert "allowed_product_logging" not in columns, f"allowed_product_logging column still exists in {table}"

        notification_columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(notification)"))}
        assert "url" not in notification_columns, "url column still exists in notification"

        # The migration must have dropped the legacy triggers that referenced the
        # removed columns (they are recreated by initialize_db() at startup).
        triggers = {
            row[0] for row in connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type='trigger'"))
        }
        assert "user_settings_before_insert" not in triggers, "user_settings_before_insert trigger was not dropped"
        assert "project_before_insert" not in triggers, "project_before_insert trigger was not dropped"

        # The seeded rows (and their surviving columns) must be preserved.
        project_row = connection.execute(
            sa.text("SELECT name FROM project WHERE object_id = :object_id"),
            {"object_id": PROJECT_ID},
        ).fetchone()
        assert project_row is not None, "Project row not found after migration"
        assert project_row[0] == "Test Project"

        settings_row = connection.execute(
            sa.text("SELECT user_reference FROM user_settings WHERE object_id = :object_id"),
            {"object_id": USER_SETTINGS_ID},
        ).fetchone()
        assert settings_row is not None, "UserSettings row not found after migration"
        assert settings_row[0] == USER_REFERENCE

        notification_row = connection.execute(
            sa.text("SELECT message FROM notification WHERE object_id = :object_id"),
            {"object_id": NOTIFICATION_ID},
        ).fetchone()
        assert notification_row is not None, "Notification row not found after migration"
        assert notification_row[0] == "Test notification"
