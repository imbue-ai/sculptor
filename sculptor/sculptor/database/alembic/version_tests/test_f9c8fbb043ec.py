import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigrationf9c8fbb043ec(MigrationTestFixture):
    """Test fixture for migration f9c8fbb043ec.

    Adds setup_command_triggered boolean column to workspace tables.
    """

    @property
    def revision(self) -> str:
        return "f9c8fbb043ec"

    @property
    def down_revision(self) -> str:
        return "9e05ec455f3d"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
