import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration9e05ec455f3d(MigrationTestFixture):
    """Test fixture for migration 9e05ec455f3d.

    Fill in seed() and verify() to test data preservation.
    See database/README.md for guidance on writing fixtures.
    """

    @property
    def revision(self) -> str:
        return "9e05ec455f3d"

    @property
    def down_revision(self) -> str:
        return "0bf9b0c50c83"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
