import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration1da4cc57bb93(MigrationTestFixture):
    """Test fixture for migration 1da4cc57bb93.

    No-op migration: adds the turn_abandoned field to RequestSuccessAgentMessage
    JSON blobs. A backwards-compatible addition with a False default, so no SQL
    changes are needed.
    """

    @property
    def revision(self) -> str:
        return "1da4cc57bb93"

    @property
    def down_revision(self) -> str:
        return "5cb094ae1d22"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
