"""Utilities for testing individual database migrations.

Each migration file must have a companion test fixture that verifies the migration
preserves data correctly. See database/README.md for guidance on writing fixtures.
"""

import importlib
import re
from abc import ABC
from abc import abstractmethod
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import StaticPool

from sculptor.database.alembic.utils import override_run_env

VERSIONS_DIR = Path(__file__).parent / "versions"
VERSION_TESTS_DIR = Path(__file__).parent / "version_tests"

# Match migration filenames like "9bb41574855c_initial.py"
_MIGRATION_FILE_PATTERN = re.compile(r"^([a-f0-9]+)_.+\.py$")

# Match test fixture filenames like "test_9bb41574855c.py"
_TEST_FILE_PATTERN = re.compile(r"^test_([a-f0-9]+)\.py$")


def get_all_migration_revision_ids() -> set[str]:
    """Return the set of revision IDs from all migration files in the versions directory."""
    revision_ids: set[str] = set()
    for path in VERSIONS_DIR.iterdir():
        if path.is_file():
            match = _MIGRATION_FILE_PATTERN.match(path.name)
            if match:
                revision_ids.add(match.group(1))
    return revision_ids


def get_all_test_fixture_revision_ids() -> set[str]:
    """Return the set of revision IDs that have corresponding test fixtures."""
    revision_ids: set[str] = set()
    for path in VERSION_TESTS_DIR.iterdir():
        if path.is_file():
            match = _TEST_FILE_PATTERN.match(path.name)
            if match:
                revision_ids.add(match.group(1))
    return revision_ids


def discover_test_fixtures() -> list["MigrationTestFixture"]:
    """Discover and instantiate all MigrationTestFixture subclasses from test files."""
    fixtures: list[MigrationTestFixture] = []
    for path in sorted(VERSION_TESTS_DIR.iterdir()):
        if not path.is_file():
            continue
        match = _TEST_FILE_PATTERN.match(path.name)
        if not match:
            continue
        module_name = f"sculptor.database.alembic.version_tests.{path.stem}"
        module = importlib.import_module(module_name)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, MigrationTestFixture) and attr is not MigrationTestFixture:
                fixtures.append(attr())
    return fixtures


class MigrationTestFixture(ABC):
    """Base class for migration data-preservation tests.

    Each migration must have a companion test fixture that inherits from this class.
    The fixture seeds the database with representative data before the migration runs,
    then verifies the data is correct after the migration completes.
    """

    @property
    @abstractmethod
    def revision(self) -> str:
        """The Alembic revision ID that this fixture tests."""
        ...

    @property
    @abstractmethod
    def down_revision(self) -> str | tuple[str, ...] | None:
        """The revision(s) that this migration depends on.

        For the initial migration, this is None.
        For regular migrations, this is a single revision ID string.
        For merge migrations, this is a tuple of revision ID strings.
        """
        ...

    def seed(self, connection: Connection) -> None:
        """Insert data into the database before the migration runs.

        Override this to seed representative data for testing.
        The database will be at the state just before this migration is applied.

        The default implementation does nothing, which is appropriate for
        no-op migrations (merge migrations, schema-only changes).
        """

    def verify(self, connection: Connection) -> None:
        """Verify data integrity after the migration runs.

        Override this to assert that data was preserved or transformed correctly.

        The default implementation does nothing, which is appropriate for
        no-op migrations (merge migrations, schema-only changes).
        """


def run_migration_fixture_test(fixture: MigrationTestFixture) -> None:
    """Run a single migration test fixture.

    1. Creates a fresh in-memory SQLite database
    2. Runs all migrations up to (but not including) the migration under test
    3. Calls fixture.seed() to insert test data
    4. Runs the migration under test
    5. Calls fixture.verify() to check data integrity
    """
    from sculptor.services.data_model_service.sql_implementation import register_all_tables

    register_all_tables()

    # Use StaticPool so all operations share the same in-memory database,
    # and skip FK enforcement since we're testing migration correctness, not FK integrity.
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})

    down_revision = fixture.down_revision
    if isinstance(down_revision, str):
        parent_revisions: tuple[str, ...] = (down_revision,)
    elif isinstance(down_revision, tuple):
        parent_revisions = down_revision
    else:
        # Initial migration (down_revision is None) — no parent revisions to apply.
        parent_revisions = ()

    # Step 1: Run migrations up to (but not including) the migration under test.
    # For merge migrations, upgrade to each parent to ensure both branches are applied.
    for parent_rev in parent_revisions:
        with engine.begin() as connection:
            with override_run_env({"connection": connection, "target_metadata": None}) as config:
                command.upgrade(config, parent_rev)

    # Step 2: Seed the database with test data
    with engine.begin() as connection:
        fixture.seed(connection)

    # Step 3: Run the migration under test
    with engine.begin() as connection:
        with override_run_env({"connection": connection, "target_metadata": None}) as config:
            command.upgrade(config, fixture.revision)

    # Step 4: Verify data integrity
    with engine.begin() as connection:
        fixture.verify(connection)
