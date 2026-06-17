"""Integration tests for Sculptor data directory migration.

Tests verify:
- In-place bootstrap creates correct directory structure when .format_version is missing
- Full migration script produces a working Sculptor folder that the backend can use
"""

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

import sculptor.primitives.ids
from imbue_core.sculptor.user_config import DependencyPaths
from imbue_core.sculptor.user_config import UserConfig
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import DependencyState
from sculptor.testing.dependency_stubs import stub_dependency
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _make_test_config() -> UserConfig:
    """Create a minimal test UserConfig."""
    test_email = "test@imbue.com"
    return UserConfig(
        user_email=test_email,
        user_id=sculptor.primitives.ids.create_user_id(test_email),
        organization_id=sculptor.primitives.ids.create_organization_id(test_email),
        instance_id=hashlib.md5(os.urandom(64)).hexdigest(),
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_llm_logs_enabled=True,
        is_session_recording_enabled=True,
        is_privacy_policy_consented=True,
        is_telemetry_level_set=True,
        dependency_paths=DependencyPaths(claude="claude"),
    )


def _populate_bootstrap_folder(folder_path: Path) -> None:
    """Set up a sculptor folder without .format_version to trigger in-place bootstrap.

    Creates the internal/ directory with config.toml (where the backend expects it)
    but omits .format_version so ensure_sculptor_folder_ready() runs bootstrap logic.
    """
    internal = folder_path / "internal"
    internal.mkdir(parents=True, exist_ok=True)
    save_config(_make_test_config(), internal / "config.toml")


def _populate_old_format_folder(folder_path: Path) -> None:
    """Create an old-format flat layout inside folder_path for the migration script.

    Old layout: config.toml, database.db, workspaces/, logs/ at the top level.
    No internal/ subdirectory, no .format_version.
    """
    save_config(_make_test_config(), folder_path / "config.toml")
    (folder_path / "workspaces").mkdir(exist_ok=True)
    (folder_path / "logs").mkdir(exist_ok=True)


def _dump_diagnostics(page: Page, sculptor_folder: Path, label: str) -> None:
    """Capture page screenshot and config for debugging CI failures."""
    screenshot_dir = Path(tempfile.mkdtemp(prefix="migration_test_diag_"))
    screenshot_path = screenshot_dir / f"{label}.png"
    page.screenshot(path=str(screenshot_path))
    print(f"\n=== MIGRATION TEST DIAGNOSTICS ({label}) ===")
    print(f"Screenshot saved to: {screenshot_path}")
    print(f"Page URL: {page.url}")
    config_path = sculptor_folder / "internal" / "config.toml"
    if config_path.exists():
        print(f"Config ({config_path}):\n{config_path.read_text()}")
    else:
        print(f"Config NOT FOUND at {config_path}")
    # Dump visible test IDs to understand what UI state we're in
    test_ids = page.evaluate("() => [...document.querySelectorAll('[data-testid]')].map(e => e.dataset.testid)")
    print(f"Visible test IDs: {test_ids}")
    print("=== END DIAGNOSTICS ===\n")


def _get_repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[4]


def _run_migration_script(home_dir: Path, dev: bool = False) -> subprocess.CompletedProcess:
    """Run the standalone migration script as a subprocess with HOME overridden."""
    cmd = [sys.executable, str(_get_repo_root() / "scripts" / "migrate_sculptor_folder.py")]
    if dev:
        cmd.append("--dev")
    env = {**os.environ, "HOME": str(home_dir)}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"Migration script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    return result


@user_story("to have Sculptor bootstrap correctly when .format_version is missing")
@custom_sculptor_folder_populator.with_args(_populate_bootstrap_folder)
@stub_dependency("claude", state=DependencyState.INSTALLED_STUB)
def test_inplace_bootstrap_and_workspace_operations(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Verify in-place bootstrap creates dirs and the frontend works afterward.

    The populator creates internal/config.toml but omits .format_version.
    On startup, ensure_sculptor_folder_ready() detects the missing version file
    and runs _bootstrap_fresh_install(), creating internal/, workspaces/, and
    .format_version. The backend then proceeds normally.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        # Verify the create surface is reachable, confirming bootstrap
        # succeeded: the topbar "+" (when workspaces exist) or the inline
        # new-workspace form's submit button (on an empty Home, where the "+"
        # is hidden).
        layout = PlaywrightProjectLayoutPage(page=page)
        modal = PlaywrightNewWorkspaceModalPage(page=page)
        try:
            expect(layout.get_add_workspace_button().or_(modal.get_submit_button())).to_be_visible(timeout=45_000)
        except AssertionError:
            _dump_diagnostics(page, instance.sculptor_folder, "bootstrap")
            raise

        # Verify bootstrap created the expected structure
        assert (instance.sculptor_folder / ".format_version").is_file()
        assert (instance.sculptor_folder / "internal").is_dir()
        assert (instance.sculptor_folder / "workspaces").is_dir()

        # Create a workspace to verify full functionality
        start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Bootstrap Test Workspace",
        )


@user_story("to migrate from old folder layout and have Sculptor work correctly")
@stub_dependency("claude", state=DependencyState.INSTALLED_STUB)
def test_full_migration_script_then_frontend(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    """Run the migration script on an old-format folder, then verify the frontend works.

    1. Creates a fake home with ~/.sculptor_data in old-format layout
    2. Runs the migration script as a subprocess
    3. Points the factory at the migrated ~/.sculptor folder
    4. Spawns a backend and verifies workspace creation works
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()

    # Create old-format layout at fake_home/.sculptor_data
    old_folder = fake_home / ".sculptor_data"
    _populate_old_format_folder(old_folder)

    # Run the migration script
    _run_migration_script(home_dir=fake_home)

    # Verify migration produced expected structure
    migrated_folder = fake_home / ".sculptor"
    assert (migrated_folder / ".format_version").is_file()
    assert (migrated_folder / "internal").is_dir()
    assert (migrated_folder / "workspaces").is_dir()
    assert (migrated_folder / "internal" / "config.toml").is_file()
    assert not old_folder.exists()

    # Point the factory at the migrated folder
    sculptor_instance_factory_.update_environment(
        sculptor_folder=migrated_folder,
        SCULPTOR_FOLDER=str(migrated_folder),
        DATABASE_URL=f"sqlite:///{migrated_folder / 'internal' / 'database.db'}",
    )

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        # Verify the create surface is reachable (see equivalent comment in
        # the bootstrap test above): the topbar "+" when workspaces exist, or
        # the inline form's submit button on an empty Home.
        layout = PlaywrightProjectLayoutPage(page=page)
        modal = PlaywrightNewWorkspaceModalPage(page=page)
        try:
            expect(layout.get_add_workspace_button().or_(modal.get_submit_button())).to_be_visible(timeout=45_000)
        except AssertionError:
            _dump_diagnostics(page, migrated_folder, "migration")
            raise

        # Create a workspace to verify full functionality
        start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Migration Test Workspace",
        )
