import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration70ec89dbef5d(MigrationTestFixture):
    """Test fixture for migration 70ec89dbef5d.

    Adds the nullable created_by (JSON) column to the workspace tables. Schema-only
    and additive — existing rows simply gain a NULL created_by — so there is no data
    to preserve or verify.
    """

    @property
    def revision(self) -> str:
        return "70ec89dbef5d"

    @property
    def down_revision(self) -> str:
        return "6026c03dc852"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
