"""Integration tests for fatal startup errors.

Covers the case where the on-disk database is stamped with an alembic revision
the running build does not know about (e.g. after a downgrade). The backend
must treat this as an unrecoverable startup error and exit promptly, so the
Electron main process can render the fatal ``BACKEND_ERROR_PAGE`` via
``BackendStatusBoundary`` instead of leaving the user stuck on the loading
screen.
"""

import hashlib
import os
from pathlib import Path

import pytest
import sqlalchemy
from playwright.sync_api import expect

import sculptor.primitives.ids
from imbue_core.async_monkey_patches_test import expect_at_least_logged_errors
from imbue_core.sculptor.user_config import DependencyPaths
from imbue_core.sculptor.user_config import UserConfig
from sculptor.database.core import create_new_engine
from sculptor.database.core import initialize_db
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.pages.error_page import PlaywrightErrorPage
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_UNKNOWN_REVISION = "unknown_future_revision_xyz"


def _make_test_user_config() -> UserConfig:
    test_email = "test@imbue.com"
    return UserConfig(
        user_email=test_email,
        user_id=sculptor.primitives.ids.create_user_id(test_email),
        organization_id=sculptor.primitives.ids.create_organization_id(test_email),
        instance_id=hashlib.md5(os.urandom(64)).hexdigest(),
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_session_recording_enabled=True,
        is_privacy_policy_consented=True,
        is_telemetry_level_set=True,
        dependency_paths=DependencyPaths(claude="claude"),
    )


def _populate_folder_with_unknown_migration_head(folder_path: Path) -> None:
    """Seed the factory's sculptor folder with a DB stamped at an unreachable revision.

    The DB lives at ``internal/database.db`` — the path the packaged backend
    binary derives from ``SCULPTOR_FOLDER``. The browser-mode factory fixture
    points ``DATABASE_URL`` at the same path so both launch modes see the
    seeded DB.
    """
    internal = folder_path / "internal"
    internal.mkdir(parents=True, exist_ok=True)
    save_config(_make_test_user_config(), internal / "config.toml")

    database_url = f"sqlite:///{internal / 'database.db'}"
    engine = create_new_engine(database_url)
    try:
        initialize_db(engine)
        with engine.begin() as connection:
            connection.execute(
                sqlalchemy.text("UPDATE alembic_version SET version_num = :rev").bindparams(rev=_UNKNOWN_REVISION)
            )
    finally:
        engine.dispose()


@user_story("to see an early error instead of a hang when my DB has a newer migration than this Sculptor build")
@custom_sculptor_folder_populator.with_args(_populate_folder_with_unknown_migration_head)
def test_unknown_migration_head_causes_backend_to_exit_not_hang(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Spawn the backend with a DB stamped at an unknown alembic revision and
    assert it refuses to start with the expected "database is not compatible"
    message rather than hanging on the loading screen.
    """
    # The harness logs a single ERROR when the backend refuses to start; declare
    # it as expected so the autouse ``explode_on_error`` fixture stays green.
    with expect_at_least_logged_errors({"Sculptor server failed to start"}):
        with pytest.raises(RuntimeError) as excinfo:
            with sculptor_instance_factory_.spawn_instance():
                pytest.fail("Backend was not supposed to become ready with an incompatible database")

    error_text = str(excinfo.value)
    assert "Sculptor database is not compatible" in error_text, (
        f"Expected the irrecoverable-error message in the backend output, got:\n{error_text}"
    )


@pytest.mark.release
@pytest.mark.packaged_electron
@user_story("to see a fatal error page instead of a hang when my DB has a newer migration than this Sculptor build")
@custom_sculptor_folder_populator.with_args(_populate_folder_with_unknown_migration_head)
def test_unknown_migration_head_renders_backend_error_page(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Under the packaged Electron binary, seed the DB with an unknown alembic
    revision and assert the renderer lands on ``BACKEND_ERROR_PAGE`` (via
    ``BackendStatusBoundary``) after the Python backend exits with the
    irrecoverable-error code.

    This end-to-end-validates the fix for the startup hang: the backend exits
    promptly, Electron main surfaces the fatal error page, and the UI shows
    the user a recoverable error rather than an indefinite loading spinner.
    """
    with sculptor_instance_factory_.spawn_instance(wait_until_ready=False) as instance:
        error_page = PlaywrightErrorPage(instance.page)
        expect(error_page.get_backend_error_page()).to_be_visible(timeout=60_000)
