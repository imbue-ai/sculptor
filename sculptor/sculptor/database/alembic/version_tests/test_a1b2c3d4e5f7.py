import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigrationa1b2c3d4e5f7(MigrationTestFixture):
    """Test fixture for migration a1b2c3d4e5f7.

    Adds is_open boolean column to workspace tables, defaulting to true.
    """

    @property
    def revision(self) -> str:
        return "a1b2c3d4e5f7"

    @property
    def down_revision(self) -> str:
        return "f9c8fbb043ec"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
