"""Integration tests for the headless/remote Claude paste-a-code sign-in flow.

These cover SCU-1502. When ``claude auth login`` can't complete a localhost
browser-loopback flow (e.g. the backend runs in a remote container), the CLI
falls back to printing a sign-in URL and waiting for the user to paste a code on
stdin. The onboarding installation step must:

1. surface that URL as a link plus a field to paste the code (instead of telling
   the user to run ``claude auth login`` in a terminal),
2. send the pasted code to the still-running CLI, and
3. only mark Claude authenticated once the CLI exits cleanly.

The flow is split across two endpoints (``POST /api/v1/dependencies/auth`` to
start and return the URL, ``POST /api/v1/dependencies/auth/code`` to submit the
code). The ``claude`` binary is stubbed by
``DependencyState.INSTALLED_NEEDS_PASTE_CODE`` to mimic that paste-a-code CLI
deterministically: its ``auth login`` prints a URL and blocks on stdin, exiting
0 only for ``CLAUDE_PASTE_CODE_VALID``.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import CLAUDE_PASTE_CODE_VALID
from sculptor.testing.dependency_stubs import DependencyState
from sculptor.testing.dependency_stubs import stub_dependency
from sculptor.testing.elements.onboarding import PlaywrightDependencyCardElement
from sculptor.testing.elements.onboarding import PlaywrightInstallationStepElement
from sculptor.testing.pages.onboarding_page import PlaywrightOnboardingPage
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_TEST_EMAIL = "test@user.com"


def _populate_with_path_mode(path: Path) -> None:
    """Write a config with ``dependency_paths.claude=PATH`` so onboarding shows the DependencyCard.

    The config has no email/consent so the onboarding wizard still triggers, and
    Claude resolves via PATH so the ``@stub_dependency`` marker's stub is used.
    """
    internal_dir = path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config = UserConfig(
        user_email="",
        user_id="paste-code-test",
        organization_id="paste-code-test",
        instance_id="paste-code-test",
        dependency_paths=DependencyPaths(claude="claude"),
    )
    save_config(config, internal_dir / "config.toml")


def _reach_claude_card(
    onboarding_page: PlaywrightOnboardingPage,
) -> tuple[PlaywrightInstallationStepElement, PlaywrightDependencyCardElement]:
    """Complete the welcome step and return the installation step + Claude card."""
    onboarding_page.get_welcome_step().complete_step(_TEST_EMAIL)
    installation_step = onboarding_page.get_installation_step()
    expect(installation_step).to_be_visible()
    return installation_step, installation_step.get_claude_card()


@user_story("to sign in to Claude in a headless/remote deployment by pasting a code")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode)
@stub_dependency("claude", state=DependencyState.INSTALLED_NEEDS_PASTE_CODE)
def test_claude_paste_code_sign_in_succeeds(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """The paste-a-code flow signs Claude in and unblocks the installation step.

    Verifies:
    1. Claude shows "not signed in" and the step is blocked
    2. Clicking Authenticate surfaces the sign-in link + a paste-a-code field
       (the headless flow does NOT self-complete)
    3. Pasting the valid code completes sign-in, the panel disappears, and the
       Continue button becomes enabled
    """
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        onboarding_page = PlaywrightOnboardingPage(sculptor_instance.page)
        installation_step, claude_card = _reach_claude_card(onboarding_page)

        expect(claude_card.get_status()).to_contain_text("not signed in")
        complete_button = installation_step.get_complete_button()
        expect(complete_button).to_be_disabled()

        # Start sign-in: the backend spawns `claude auth login`, which (headless)
        # prints a URL and blocks waiting for a pasted code instead of completing.
        claude_card.get_authenticate_button().click()

        # The paste-a-code panel appears: a sign-in link plus a code field.
        # (Default 30s timeout covers the backend round-trip that reads the URL.)
        expect(claude_card.get_auth_url_link()).to_be_visible(timeout=30000)
        expect(claude_card.get_auth_code_input()).to_be_visible()

        # Paste the code the (stub) sign-in page would have shown, then submit it.
        claude_card.get_auth_code_input().fill(CLAUDE_PASTE_CODE_VALID)
        claude_card.get_auth_code_submit().click()

        # The CLI exits cleanly, auth re-checks as authenticated, and the step
        # unblocks. The paste-a-code panel is dismissed.
        expect(complete_button).to_contain_text("Continue", timeout=30000)
        expect(claude_card.get_auth_panel()).not_to_be_visible()


@user_story("to see an error when I paste an invalid Claude sign-in code")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode)
@stub_dependency("claude", state=DependencyState.INSTALLED_NEEDS_PASTE_CODE)
def test_claude_paste_code_invalid_code_shows_error(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """An invalid pasted code surfaces an inline error and leaves the step blocked.

    Verifies:
    1. Clicking Authenticate surfaces the paste-a-code field
    2. Submitting a wrong code shows the CLI's error inline
    3. Sign-in did not complete: the Continue button stays disabled
    """
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        onboarding_page = PlaywrightOnboardingPage(sculptor_instance.page)
        installation_step, claude_card = _reach_claude_card(onboarding_page)

        claude_card.get_authenticate_button().click()
        expect(claude_card.get_auth_code_input()).to_be_visible(timeout=30000)

        # A wrong code makes the (stub) CLI exit non-zero; the error surfaces inline.
        claude_card.get_auth_code_input().fill("definitely-not-the-code")
        claude_card.get_auth_code_submit().click()

        expect(claude_card.get_auth_error()).to_be_visible(timeout=30000)

        # Sign-in did not complete, so the step stays blocked.
        expect(installation_step.get_complete_button()).to_be_disabled()
