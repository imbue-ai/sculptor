import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigration70ec89dbef5d(MigrationTestFixture):
    """Test fixture for migration 70ec89dbef5d.

    Adds the nullable created_by (JSON) column to the workspace tables. Schema-only
    and additive — existing rows simply gain a NULL created_by — so there is no data
    to preserve; verify() just asserts the column landed on both tables.
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
        # The two-table (`<name>` / `<name>_latest`) design means both tables must
        # gain the column; assert it rather than trusting the migration blindly.
        inspector = sa.inspect(connection)
        for table in ("workspace", "workspace_latest"):
            columns = {column["name"] for column in inspector.get_columns(table)}
            assert "created_by" in columns, f"created_by column missing from {table} after migration"
