"""Integration test for blocked Claude Code versions.

Scenario: A Claude binary reports a version that falls within the allowed
range but is explicitly blocked. The onboarding installation step should
show the version in error styling and prevent the user from continuing
(showing "Check Now" instead of "Continue").

Setup strategy
--------------
1. Use create_claude_version_stub_dir() to create a stub "claude" that
   reports the blocked version (2.1.101).
2. Write the stub's absolute path into the config as
   ``dependency_paths.claude`` so the server resolves the binary directly.
3. Use a custom sculptor folder populator that leaves email empty so
   onboarding still triggers.
4. Complete the welcome step, then verify the installation step shows
   the blocked version and does not offer "Continue".
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.foundation.user_config import DependencyPaths
from sculptor.foundation.user_config import UserConfig
from sculptor.services.dependency_management_service import CLAUDE_VERSION_RANGE
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import create_claude_version_stub_dir
from sculptor.testing.pages.onboarding_page import PlaywrightOnboardingPage
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BLOCKED_VERSION = CLAUDE_VERSION_RANGE.blocked_versions[0].min_version


def _populate_with_blocked_stub(stub_path: str) -> callable:
    """Return a populator that writes a config pointing at the given stub path."""

    def _populate(path: Path) -> None:
        internal_dir = path / "internal"
        internal_dir.mkdir(parents=True, exist_ok=True)
        config = UserConfig(
            user_email="",
            user_id="blocked-version-test",
            organization_id="blocked-version-test",
            instance_id="blocked-version-test",
            dependency_paths=DependencyPaths(claude=stub_path),
        )
        save_config(config, internal_dir / "config.toml")

    return _populate


@user_story("to see that a blocked Claude version prevents onboarding from completing")
def test_blocked_version_shows_out_of_range(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    """When the installed Claude binary reports a blocked version, the
    onboarding installation step should show the version and the submit
    button should say "Check Now" instead of "Continue"."""
    stub_dir = create_claude_version_stub_dir(tmp_path, _BLOCKED_VERSION)
    stub_path = stub_dir / "claude"

    # Write the stub path into the sculptor folder config so the server
    # resolves it directly. We must do this before spawning the instance.
    populator = _populate_with_blocked_stub(str(stub_path))
    populator(sculptor_instance_factory_._delegate.sculptor_folder)

    with sculptor_instance_factory_.spawn_instance(auto_project=False) as instance:
        onboarding_page = PlaywrightOnboardingPage(instance.page)

        # Complete the welcome step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step("test@blocked-version.com")

        # On the installation step, the blocked version should be visible
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Expand the claude card to see version details
        claude_card = installation_step.get_claude_card()
        expect(claude_card.get_status()).to_contain_text("version mismatch")
        claude_card.locator.click()

        claude_version = claude_card.get_version()
        expect(claude_version).to_contain_text(_BLOCKED_VERSION)

        # The Continue button should be disabled because the blocked version
        # fails the is_version_in_range check.
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_be_disabled()
