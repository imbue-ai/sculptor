import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigrationf332049181c5(MigrationTestFixture):
    """Test fixture for migration f332049181c5.

    Adds the setup_command column to the workspace tables. Schema-only —
    no data preservation to verify.
    """

    @property
    def revision(self) -> str:
        return "f332049181c5"

    @property
    def down_revision(self) -> str:
        return "35cc9f0245b6"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
