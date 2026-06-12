import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture

EXPECTED_TABLES = {
    "project",
    "project_latest",
    "task",
    "task_latest",
    "user_settings",
    "user_settings_latest",
    "notification",
    "saved_agent_message",
}


class TestInitialMigration(MigrationTestFixture):
    """Test fixture for the initial migration that creates all tables."""

    @property
    def revision(self) -> str:
        return "9bb41574855c"

    @property
    def down_revision(self) -> None:
        return None

    def verify(self, connection: sa.engine.Connection) -> None:
        result = connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result}
        for expected in EXPECTED_TABLES:
            assert expected in tables, f"Expected table '{expected}' not found"
