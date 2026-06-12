import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration059f36aaa193(MigrationTestFixture):
    """Test fixture for migration 059f36aaa193.

    Fill in seed() and verify() to test data preservation.
    See database/README.md for guidance on writing fixtures.
    """

    @property
    def revision(self) -> str:
        return "059f36aaa193"

    @property
    def down_revision(self) -> str:
        return "c8d4e5f6a7b8"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
