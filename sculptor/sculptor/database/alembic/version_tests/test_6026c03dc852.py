import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration6026c03dc852(MigrationTestFixture):
    """Test fixture for migration 6026c03dc852.

    No-op migration: removes the last_processed_message_id field from
    AgentTaskStateV2 JSON blobs. Old rows keep the key; it is an extra key
    that is ignored on validate, so no SQL changes are needed.
    """

    @property
    def revision(self) -> str:
        return "6026c03dc852"

    @property
    def down_revision(self) -> str:
        return "1da4cc57bb93"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
