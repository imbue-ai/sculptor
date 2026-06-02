"""Integration tests for the Claude binary installation feature."""

import re
import shutil
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.services.dependency_management_service import DEPENDENCIES_DIR_NAME
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import DependencyState
from sculptor.testing.dependency_stubs import stub_dependency
from sculptor.testing.elements.version_popover import PlaywrightVersionPopoverElement
from sculptor.testing.pages.onboarding_page import PlaywrightOnboardingPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# Mark for tests that hit external services (download from the internet, etc.)
external_deps = pytest.mark.external_deps

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _populate_with_custom_mode(path: Path) -> None:
    """Write a config with dependency_paths.claude=claude so the instance uses custom mode.

    The config has no email/consent so onboarding still triggers.
    """
    internal_dir = path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config = UserConfig(
        user_email="",
        user_id="claude-install-test",
        organization_id="claude-install-test",
        instance_id="claude-install-test",
        dependency_paths=DependencyPaths(claude="claude"),
    )
    save_config(config, internal_dir / "config.toml")


def _populate_with_managed_mode(path: Path) -> None:
    """Write a config with dependency_paths.claude=MANAGED (default).

    The config has no email/consent so onboarding still triggers.
    """
    internal_dir = path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config = UserConfig(
        user_email="",
        user_id="claude-install-test",
        organization_id="claude-install-test",
        instance_id="claude-install-test",
        dependency_paths=DependencyPaths(claude="MANAGED"),
    )
    save_config(config, internal_dir / "config.toml")


def _delete_managed_claude_cache(sculptor_folder: Path) -> None:
    """Remove any cached managed Claude binaries so a fresh install is required."""
    claude_dir = sculptor_folder / "internal" / DEPENDENCIES_DIR_NAME / "claude"
    if claude_dir.exists():
        shutil.rmtree(claude_dir)


# ---------------------------------------------------------------------------
# Settings section tests
# ---------------------------------------------------------------------------


@pytest.mark.release
@user_story("to see Claude CLI configuration in Settings")
def test_settings_claude_cli_section_visible(sculptor_instance_: SculptorInstance) -> None:
    """Test that the Claude CLI settings section is visible with mode selector and status."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    claude_section = settings_page.click_on_dependencies()

    expect(claude_section.get_mode_selector()).to_be_visible()
    expect(claude_section.get_status()).to_be_visible()
    # When Claude is healthy and managed, the compact view shows "Up to date"
    # instead of the detailed version/path rows.
    up_to_date = claude_section.get_up_to_date()
    version = claude_section.get_version()
    expect(up_to_date.or_(version)).to_be_visible()


@pytest.mark.release
@user_story("to persist my Claude CLI mode selection across navigation")
def test_settings_mode_selector_persists(sculptor_instance_: SculptorInstance) -> None:
    """Test that changing the mode selector persists when navigating away and back.

    Steps:
    1. Navigate to Dependencies settings
    2. Change mode to "Custom"
    3. Wait for the status to settle (not showing a spinner)
    4. Navigate to General settings (away from Dependencies)
    5. Navigate back to Dependencies settings
    6. Verify mode is still "Custom"
    """
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)
    claude_section = settings_page.click_on_dependencies()

    mode_selector = claude_section.get_mode_selector()
    expect(mode_selector).to_be_visible()

    # Switch to "Custom"
    mode_selector.click()
    custom_option = claude_section.get_mode_option_custom()
    expect(custom_option).to_be_visible()
    custom_option.click()

    # The selector shows "Custom" immediately (via pending local state)
    expect(mode_selector).to_contain_text("Custom")

    # Wait for the settling spinner to disappear — this means the save + fetch
    # has completed and the dependencies atom is up to date.
    settling_spinner = claude_section.get_settling_spinner()
    expect(settling_spinner).to_have_count(0)

    # Navigate away (General) and back (Dependencies)
    settings_page.click_on_general()
    claude_section = settings_page.click_on_dependencies()

    # Verify the mode persisted after remount
    mode_selector = claude_section.get_mode_selector()
    expect(mode_selector).to_contain_text("Custom")


@pytest.mark.release
@user_story("to see the install button when Claude is in managed mode")
def test_settings_managed_mode_shows_install_button(sculptor_instance_: SculptorInstance) -> None:
    """Test that the managed mode shows the install button or 'Up to date' status.

    The install button is visible when managed mode is active and the binary
    is not yet installed or out of range. If the binary is already installed
    and in range, 'Up to date' is shown instead.
    """
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)
    claude_section = settings_page.click_on_dependencies()

    # Switch to managed mode
    mode_selector = claude_section.get_mode_selector()
    expect(mode_selector).to_be_visible()
    mode_selector.click()
    managed_option = claude_section.get_mode_option_managed()
    expect(managed_option).to_be_visible()
    managed_option.click()

    # Wait for the mode change to settle (WebSocket confirms the new mode).
    # The frontend has a 10s timeout that reverts displayMode if the WebSocket
    # doesn't confirm in time (SCU-441).  On slower runners, the round-trip
    # can exceed 10s, causing the managed section to disappear.  If the mode
    # reverted, re-select managed and wait again.
    settling_spinner = claude_section.get_settling_spinner()
    expect(settling_spinner).to_have_count(0, timeout=30_000)
    if "Custom" in (mode_selector.text_content() or ""):
        mode_selector.click()
        expect(managed_option).to_be_visible()
        managed_option.click()
        expect(settling_spinner).to_have_count(0, timeout=30_000)

    # Wait for a terminal managed-mode state (install button or "up to date").
    install_button = claude_section.get_install_button()
    up_to_date = claude_section.get_up_to_date()
    expect(install_button.or_(up_to_date)).to_be_visible(timeout=60_000)

    # Restore to Custom mode to avoid managed auto-install polluting shared instance state
    mode_selector = claude_section.get_mode_selector()
    mode_selector.click()
    custom_option = claude_section.get_mode_option_custom()
    expect(custom_option).to_be_visible()
    custom_option.click()


@pytest.mark.release
@user_story("to see Claude CLI version in the version popover")
def test_version_popover_shows_claude_cli_info(sculptor_instance_: SculptorInstance) -> None:
    """Test that the version popover displays Claude CLI version and mode."""
    page = sculptor_instance_.page

    version_popover = PlaywrightVersionPopoverElement(page)
    version_popover.open()
    expect(version_popover).to_be_visible()

    expect(version_popover.get_claude_cli_version()).to_be_visible()
    expect(version_popover.get_claude_cli_mode()).to_be_visible()


@pytest.mark.release
@user_story("to see Git dependency status in Settings")
def test_settings_git_section_visible(sculptor_instance_: SculptorInstance) -> None:
    """Test that the Git section is visible in Dependencies settings with status."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    deps_section = settings_page.click_on_dependencies()

    git_status = deps_section.get_git_status()
    expect(git_status).to_be_visible()
    # Git should be installed in the test environment
    expect(git_status).to_contain_text("Installed")


# ---------------------------------------------------------------------------
# Onboarding tests
# ---------------------------------------------------------------------------


@user_story("to see that Claude is not found during onboarding and can use a custom path")
@custom_sculptor_folder_populator.with_args(_populate_with_custom_mode)
@stub_dependency("claude", state=DependencyState.NOT_INSTALLED)
def test_onboarding_claude_not_found_shows_override(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test that onboarding shows Claude as not found with an override link.

    Verifies:
    1. Claude card shows not-found state
    2. Override link is visible for manual path entry
    3. Complete button is disabled (blocked)
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # Complete email step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        # Verify installation step loads
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Claude card should show not-found state
        claude_card = installation_step.get_claude_card()
        expect(claude_card.locator).to_be_visible()

        # Expand to see override link
        claude_card.locator.click()

        override_link = claude_card.get_override_link()
        expect(override_link).to_be_visible()

        # Complete button should be disabled since Claude is missing
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_be_visible()
        expect(complete_button).to_be_disabled()


@user_story("to enter a custom Claude path during onboarding and see an error for invalid paths")
@custom_sculptor_folder_populator.with_args(_populate_with_custom_mode)
@stub_dependency("claude", state=DependencyState.NOT_INSTALLED)
def test_onboarding_claude_override_invalid_path(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test that entering an invalid path in the Claude override shows an error.

    Verifies:
    1. Clicking override link shows input field
    2. Entering an invalid path and clicking Apply shows an error
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Expand the card to see override link
        claude_card = installation_step.get_claude_card()
        expect(claude_card.locator).to_be_visible()

        claude_card.locator.click()

        # Click override link
        override_link = claude_card.get_override_link()
        expect(override_link).to_be_visible()
        override_link.click()

        # Override input should appear
        override_input = claude_card.get_override_input()
        expect(override_input).to_be_visible()

        # Enter invalid path and apply
        override_input.fill("/nonexistent/path/to/claude")
        apply_button = claude_card.get_override_apply()
        apply_button.click()

        # Error should appear
        error = claude_card.get_override_error()
        expect(error).to_be_visible()
        expect(error).to_contain_text("No executable found")


# ---------------------------------------------------------------------------
# Real installation tests (require internet access)
# ---------------------------------------------------------------------------

INSTALL_TIMEOUT_MS = 120_000


@pytest.mark.release
@external_deps
@pytest.mark.skip(reason="TODO(SCU-355): sculptor_instance_factory_ not yet supported in packaged mode")
@user_story("to have Claude automatically installed during onboarding in managed mode")
@custom_sculptor_folder_populator.with_args(_populate_with_managed_mode)
def test_onboarding_managed_mode_auto_installs_claude(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Onboarding in MANAGED mode automatically downloads and installs Claude.

    Steps:
    1. Start Sculptor with MANAGED mode config and no cached binary
    2. Complete the email step
    3. Reach the installation step — the wizard auto-triggers install
    4. Wait for the install to finish (complete button text changes to "Continue")
    5. Verify the Claude version is visible on the card
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        # Ensure no cached binary so a real download occurs
        _delete_managed_claude_cache(sculptor_instance.sculptor_folder)

        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # Complete email step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        # Reach installation step — auto-install triggers for MANAGED mode
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Wait for the install to complete: the button becomes enabled
        # once all deps are healthy.
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_contain_text("Continue", timeout=INSTALL_TIMEOUT_MS)

        # Claude version should now be visible on the card
        claude_card = installation_step.get_claude_card()
        expect(claude_card.get_version()).to_be_visible()


@pytest.mark.release
@external_deps
@pytest.mark.skip(reason="TODO(SCU-355): sculptor_instance_factory_ not yet supported in packaged mode")
@user_story("to install Claude via the Settings page when the managed binary is missing")
def test_settings_install_managed_binary(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Trigger a managed Claude install from the Settings page.

    Uses sculptor_instance_factory_ so we can delete the cached binary
    before the instance starts, ensuring the backend reports the binary
    as missing from the first status push.

    Steps:
    1. Delete the cached managed binary before spawning the instance
    2. Navigate to Settings > Dependencies
    3. Ensure managed mode is selected
    4. Click the install button
    5. Wait for "Up to date" to appear
    6. Verify the version display is populated
    """
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        settings_page = navigate_to_settings_page(page=page)
        claude_section = settings_page.click_on_dependencies()

        # Wait for the dependency status atom to load via WebSocket before
        # interacting with the mode selector. Until the atom loads, the Select
        # defaults to "Managed" (the null-atom fallback), and re-selecting
        # "Managed" won't fire onValueChange if the value hasn't changed.
        # We detect the atom has loaded by waiting for the version display
        # to show something other than the null-state default.
        status = claude_section.get_status()
        expect(status).to_contain_text(
            re.compile(r"Version in range|Out of range|Not installed|No path configured"),
        )

        # Ensure managed mode is selected
        mode_selector = claude_section.get_mode_selector()
        expect(mode_selector).to_be_visible()
        mode_selector.click()
        managed_option = claude_section.get_mode_option_managed()
        expect(managed_option).to_be_visible()
        managed_option.click()

        # The install button should be visible (no cached binary)
        install_button = claude_section.get_install_button()
        expect(install_button).to_be_visible()
        install_button.click()

        # Wait for install to complete — "Up to date" text appears
        up_to_date = claude_section.get_up_to_date()
        expect(up_to_date).to_be_visible(timeout=INSTALL_TIMEOUT_MS)

        # Version should now be populated
        version = claude_section.get_version()
        expect(version).not_to_have_text("Not installed")
