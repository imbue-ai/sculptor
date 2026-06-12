import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration0bf9b0c50c83(MigrationTestFixture):
    """Test fixture for migration 0bf9b0c50c83.

    Adds a composite index on saved_agent_message (task_id, created_at)
    to eliminate full table scans during startup message loading.
    """

    @property
    def revision(self) -> str:
        return "0bf9b0c50c83"

    @property
    def down_revision(self) -> str:
        return "bcc42be33ebc"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        result = connection.execute(sa.text("PRAGMA index_list('saved_agent_message')"))
        index_names = [row[1] for row in result.fetchall()]
        assert "ix_saved_agent_message_task_id_created_at" in index_names
