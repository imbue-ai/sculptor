"""Integration tests for Sculptor data directory bootstrap.

Tests verify:
- Bootstrap creates correct directory structure when .format_version is missing
"""

import hashlib
import os
import tempfile
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

import sculptor.primitives.ids
from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
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
