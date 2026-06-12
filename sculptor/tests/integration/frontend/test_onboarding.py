"""Integration tests for the onboarding flow."""

from pathlib import Path

import pytest
from loguru import logger
from playwright.sync_api import expect

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import DependencyState
from sculptor.testing.dependency_stubs import stub_dependency
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.onboarding_page import PlaywrightOnboardingPage
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _dont_populate_sculptor_folder(path: Path) -> None:
    logger.info("Skipping population of Sculptor folder for onboarding test.")


def _populate_with_path_mode(path: Path) -> None:
    """Write a config with dependency_paths.claude=PATH so onboarding uses DependencyCard.

    The config has no email/consent so onboarding still triggers.
    # TODO(SCU-162): Transition these tests to exercise the managed install flow instead.
    """
    internal_dir = path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config = UserConfig(
        user_email="",
        user_id="onboarding-test",
        organization_id="onboarding-test",
        instance_id="onboarding-test",
        dependency_paths=DependencyPaths(claude="claude"),
    )
    save_config(config, internal_dir / "config.toml")


@custom_sculptor_folder_populator.with_args(_populate_with_path_mode)
def test_full_onboarding_flow(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test the complete onboarding flow from welcome step through to the Add Workspace page.

    Verifies:
    1. Welcome step loads and accepts email
    2. Installation step loads with telemetry options
    3. Add repo step accepts a repository path
    4. After completing onboarding, the Add Workspace page is shown
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance(auto_project=False) as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # Complete email step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        # Complete installation step (select telemetry, click continue)
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()
        installation_step.complete_step()

        # Complete add-repo step
        add_repo_step = onboarding_page.get_add_repo_step()
        expect(add_repo_step).to_be_visible()
        add_repo_step.complete_step(str(sculptor_instance_factory_.base_repo.base_path))

        # After onboarding, the Add Workspace page should load
        add_workspace_page = PlaywrightAddWorkspacePage(page)
        expect(add_workspace_page.get_submit_button()).to_be_visible()


@user_story("to see a descriptive validation error when my email is rejected during onboarding")
@custom_sculptor_folder_populator.with_args(_dont_populate_sculptor_folder)
def test_invalid_email_surfaces_validation_error(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """A backend 422 during the email step must surface the field validation message.

    Regression test for SCU-1365. ``makeAPIRequest``
    (``sculptor/frontend/src/apiClient.ts``) only threw ``ValidationError`` when
    ``errorData.status === 422``, but a FastAPI 422 body is ``{"detail": [...]}``
    with no top-level ``status`` field — so that branch was unreachable (and it
    threw from inside a ``try``/``catch`` that swallowed the error anyway). As a
    result, onboarding email-validation failures were replaced by an opaque
    ``HTTP 422`` message with no field-level detail.

    ``foo@bar`` clears the client-side ``email.includes("@")`` gate but fails the
    backend's ``EmailStr`` validation, producing a real 422 with a ``detail`` array.

    Verifies:
    1. The welcome step accepts and submits the invalid email
    2. The descriptive field-validation message is shown (correct behavior)
    3. The opaque ``HTTP 422`` fallback is NOT shown (the bug)
    """
    invalid_email = "foo@bar"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        expect(welcome_step).to_be_visible()

        # An email that passes the client-side gate but fails backend validation.
        welcome_step.enter_email(invalid_email)
        welcome_step.submit()

        # The inline error must show the validation message from the 422 ``detail``
        # array — not the opaque "HTTP 422" fallback. (Default 30s timeout: this
        # waits on a backend round-trip.)
        error_message = welcome_step.get_error_message()
        expect(error_message).to_contain_text("is not a valid email address")
        expect(error_message).not_to_contain_text("HTTP 422")


@user_story("to sign up for Sculptor even when Git is not installed")
@custom_sculptor_folder_populator.with_args(_dont_populate_sculptor_folder)
@stub_dependency("git", state=DependencyState.NOT_INSTALLED)
def test_onboarding_without_git_installed(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test that a user can reach the onboarding page when Git is not installed.

    Verifies:
    1. The onboarding page loads successfully (gets past startup/health boundaries)
    2. The Git status shows an "Install" button (indicating Git is NOT installed)
    3. The complete button is disabled (signup is blocked until Git is installed)
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        onboarding_page = PlaywrightOnboardingPage(sculptor_instance.page)

        # Complete email step to get to the installation step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        # Verify we can reach the installation step
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Verify Git card is visible and shows "Install" button (Git is NOT installed)
        git_card = installation_step.get_git_card()
        expect(git_card.locator).to_be_visible()

        # Verify it shows "Install" button, not "Installed" text
        expect(git_card.get_status()).not_to_contain_text("Installed")
        expect(git_card.get_install_button()).to_be_visible()

        # Verify the complete button is disabled since requirements aren't met
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_be_visible()
        expect(complete_button).to_be_disabled()


@user_story("to see where dependencies were found and their versions")
@custom_sculptor_folder_populator.with_args(_dont_populate_sculptor_folder)
def test_dependency_path_and_version_display(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test that path and version info are shown for installed dependencies.

    Verifies:
    1. Git card shows the resolved path
    2. Git card shows the version
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Expand the Git card to see path/version details
        git_card = installation_step.get_git_card()
        expect(git_card.locator).to_be_visible()
        # The card mirrors its `canExpand` gate via `aria-disabled`, so this click
        # auto-waits for the dependency probe to settle (SCU-1215) — no precondition needed.
        git_card.locator.click()

        # Git should show path and version (Git is installed in test environments)
        expect(git_card.get_path()).to_be_visible()
        expect(git_card.get_version()).to_be_visible()

        # Override link should be available
        expect(git_card.get_override_link()).to_be_visible()


@user_story("to see an error when entering an invalid dependency override path")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode)
@stub_dependency("claude", state=DependencyState.NOT_INSTALLED)
def test_invalid_override_path_shows_error(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test that entering a nonexistent path shows an error.

    Verifies:
    1. Claude card shows not-found state with override link
    2. Clicking override link shows input field
    3. Entering invalid path and clicking Apply shows error
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Expand the Claude card to see override link
        claude_card = installation_step.get_claude_card()
        expect(claude_card.locator).to_be_visible()
        claude_card.locator.click()

        # Claude card should show override link (not found state)
        override_link = claude_card.get_override_link()
        expect(override_link).to_be_visible()
        override_link.click()

        # Override input should appear
        override_input = claude_card.get_override_input()
        expect(override_input).to_be_visible()

        # Enter invalid path
        override_input.fill("/nonexistent/path/to/claude")

        # Click apply
        claude_card.get_override_apply().click()

        # Error should appear
        error = claude_card.get_override_error()
        expect(error).to_be_visible()
        expect(error).to_contain_text("No executable found")


@user_story("to see that Claude is not found and the override link is available")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode)
@stub_dependency("claude", state=DependencyState.NOT_INSTALLED)
def test_onboarding_without_claude_installed(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test the onboarding page when Claude CLI is not installed.

    Verifies:
    1. Claude card shows not-found state
    2. Override link is visible with manual path option
    3. Complete button is disabled (blocked)
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Claude card should be visible
        claude_card = installation_step.get_claude_card()
        expect(claude_card.locator).to_be_visible()

        # Expand to see override link
        claude_card.locator.click()

        # Override link should show the manual path option
        expect(claude_card.get_override_link()).to_be_visible()

        # Complete button should be disabled since Claude is missing
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_be_visible()
        expect(complete_button).to_be_disabled()


@user_story("to see that Claude needs authentication and authenticate it")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode)
@stub_dependency("claude", state=DependencyState.INSTALLED_NOT_AUTHENTICATED)
def test_claude_not_authenticated(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test the auth flow when Claude is installed but not authenticated.

    Verifies:
    1. Claude card shows "not signed in" state
    2. Authenticate button is visible
    3. Complete button is disabled (blocked)
    4. Clicking Authenticate triggers the auth flow
    5. After auth, Complete button becomes "Continue"
    """
    test_email = "test@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Claude card should show "not signed in"
        claude_card = installation_step.get_claude_card()
        expect(claude_card.get_status()).to_contain_text("not signed in")

        # Authenticate button should be visible
        auth_button = claude_card.get_authenticate_button()
        expect(auth_button).to_be_visible()

        # Complete button should be disabled (blocked)
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_be_disabled()

        # Click authenticate
        auth_button.click()

        # After auth completes, the button should become "Continue"
        expect(complete_button).to_contain_text("Continue", timeout=30000)


@user_story("to return to the welcome step and see my previously entered email preserved")
@custom_sculptor_folder_populator.with_args(_dont_populate_sculptor_folder)
def test_back_navigation_preserves_email(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Test that navigating back from the installation step preserves the email.

    Verifies:
    1. Email entered in step 1 is preserved after navigating back via step indicator
    """
    test_email = "backtest@user.com"
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # Complete email step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        # Verify installation step loads
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Go back via the step indicator (click the first dot to return to step 1)
        onboarding_page.get_step_indicator_dot(0).click()

        # Welcome step should be visible again
        welcome_step = onboarding_page.get_welcome_step()
        expect(welcome_step).to_be_visible()

        # Email should be preserved
        email_input = welcome_step.get_email_input()
        expect(email_input).to_have_value(test_email)


@pytest.mark.skip(reason="Onboarding wizard advances before config is persisted; refresh sees stale config status")
@user_story("to stay on the add-repo step after refreshing the page")
@custom_sculptor_folder_populator.with_args(_dont_populate_sculptor_folder)
def test_refresh_on_add_repo_step_returns_to_add_repo(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Test that refreshing the page on the add-repo step returns to add-repo, not the workspace page.

    Verifies:
    1. After completing email and installation steps, user reaches add-repo step
    2. After page refresh, user is shown the add-repo step (not the workspace page)
    """
    test_email = "refresh@test.com"
    with sculptor_instance_factory_.spawn_instance(auto_project=False) as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # Complete email step
        welcome_step = onboarding_page.get_welcome_step()
        welcome_step.complete_step(test_email)

        # Complete installation step
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()
        installation_step.complete_step()

        # Verify we reached the add-repo step
        add_repo_step = onboarding_page.get_add_repo_step()
        expect(add_repo_step).to_be_visible()

        # Refresh the page via soft_reload_page (re-navigate to the
        # current URL) to avoid ERR_INSUFFICIENT_RESOURCES on CI runners.
        soft_reload_page(page)

        # After refresh, the add-repo step should be shown again (not the workspace page)
        add_repo_step = onboarding_page.get_add_repo_step()
        expect(add_repo_step).to_be_visible(timeout=30000)


def _populate_with_email_no_privacy(path: Path) -> None:
    """Write a config with email set but without privacy consent or telemetry level.

    Simulates a returning user who has an email and an existing project but needs to
    complete their privacy/telemetry settings (e.g. after a fresh install).
    """
    internal_dir = path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config = UserConfig(
        user_email="returning@user.com",
        user_id="returning-user-test",
        organization_id="returning-user-test-org",
        instance_id="returning-user-test-instance",
        dependency_paths=DependencyPaths(claude="claude"),
    )
    save_config(config, internal_dir / "config.toml")


@user_story("to skip the add-repo step when I already have a repo configured")
@custom_sculptor_folder_populator.with_args(_populate_with_email_no_privacy)
def test_installation_step_skips_add_repo_when_project_exists(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Completing the installation step should not show the add-repo step if a project already exists.

    A returning user with an existing project who needs to complete their privacy/telemetry
    settings should be sent straight to the main app after the installation step —
    not to the "Add your first repo" page.

    Verifies:
    1. User with email + project but no privacy settings is routed to the installation step
    2. After completing the installation step, the add-repo step does NOT appear
    3. The main app (Add Workspace page) is shown instead
    """
    with sculptor_instance_factory_.spawn_instance(auto_project=True) as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # User is routed to the installation step (has email + project, but no privacy consent)
        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # Wait for deps to be verified so the "Continue" button is enabled
        expect(installation_step.get_complete_button()).to_contain_text("Continue")

        # Complete the installation step
        installation_step.complete_step()

        # The main app should appear — not the add-repo step
        add_workspace_page = PlaywrightAddWorkspacePage(page)
        expect(add_workspace_page.get_submit_button()).to_be_visible()

        # The add-repo step should not have appeared
        expect(onboarding_page.get_add_repo_step()).not_to_be_visible()
