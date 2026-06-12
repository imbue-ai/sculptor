import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigrationb5a4106e6118(MigrationTestFixture):
    """Test fixture for migration b5a4106e6118.

    Adds the setup state columns (status, run_id, exit_code, started_at,
    finished_at, log_path, log_truncated) to the workspace tables.
    """

    @property
    def revision(self) -> str:
        return "b5a4106e6118"

    @property
    def down_revision(self) -> str:
        return "c8d4e5f6a7b8"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
