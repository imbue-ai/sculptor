import sqlalchemy as sa

from sculptor.database.alembic.migration_test_utils import MigrationTestFixture


class TestMigrationeedceaef0697(MigrationTestFixture):
    """Test fixture for migration eedceaef0697.

    No-op migration: adds turn_metrics, stopped, and interrupted fields
    to chat message JSON blobs. All are backwards-compatible additions
    with sensible defaults (None / False), so no SQL changes are needed.
    """

    @property
    def revision(self) -> str:
        return "eedceaef0697"

    @property
    def down_revision(self) -> str:
        return "d58cd1a270b9"

    def seed(self, connection: sa.engine.Connection) -> None:
        pass

    def verify(self, connection: sa.engine.Connection) -> None:
        pass
