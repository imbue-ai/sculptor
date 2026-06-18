"""End-to-end tests for the telemetry opt-out (SCU-1291).

Behaviors covered:

Settings → Privacy (shared instance, seeded with telemetry on):
1. The Privacy section is reachable from the settings nav and shows the
   account email and the telemetry switch in the on position.
2. Turning telemetry off asks for confirmation; cancelling leaves the switch
   and the persisted flags untouched.
3. Confirming the opt-out flips all SDK-facing flags off in the persisted
   config and unchecks the switch.
4. Turning telemetry back on is instant (no dialog) and restores the flags.
5. ``PUT /api/v1/config`` rejects telemetry-flag changes with a 400 pointing
   at the dedicated endpoint, while a no-op value passes through.

Onboarding (fresh instances):
6. The welcome step shows the telemetry checkbox pre-checked and the
   "Continue without an account" skip link.
7. Submitting an email with the checkbox unchecked persists the account with
   all telemetry flags off.
8. Skipping account setup completes onboarding without an email: the config
   stays anonymous with privacy consent recorded, the full wizard can finish
   (empty email is accepted), Settings → Privacy shows the email as "Unset",
   and a reload routes back into the app instead of the wizard.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.onboarding_page import PlaywrightOnboardingPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_TELEMETRY_FLAG_KEYS = ("isErrorReportingEnabled", "isProductAnalyticsEnabled", "isSessionRecordingEnabled")


def _get_user_config(instance: SculptorInstance) -> dict:
    """Fetch the persisted user config through the backend API."""
    base_url = instance.backend_api_url.rstrip("/")
    response = instance.page.request.get(f"{base_url}/api/v1/config")
    assert response.ok, f"GET /api/v1/config failed: {response.status}"
    return response.json()


@user_story("to opt out of all telemetry from the settings page and opt back in")
def test_privacy_settings_telemetry_switch(sculptor_instance_: SculptorInstance) -> None:
    """The Privacy section's telemetry switch flips the persisted consent.

    Verifies behaviors 1-4: section contents, the cancel path, the confirmed
    opt-out (all flags off), and the dialog-free opt-in (flags back on).

    Note: the opt-in path deliberately leaves ``isSessionRecordingEnabled``
    off — session recording is excluded from the binary consent — so this
    test also pins that the seeded ``True`` value does not come back.
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    privacy_section = settings_page.click_on_privacy()

    # 1. Email and the enabled switch are shown.
    expect(privacy_section.get_email_field()).to_contain_text("test@imbue.com")
    telemetry_switch = privacy_section.get_telemetry_switch()
    expect(telemetry_switch).to_have_attribute("data-state", "checked")

    # 2. Cancelling the opt-out dialog changes nothing.
    telemetry_switch.click()
    expect(privacy_section.get_opt_out_dialog()).to_be_visible()
    privacy_section.get_opt_out_cancel_button().click()
    expect(privacy_section.get_opt_out_dialog()).not_to_be_visible()
    expect(telemetry_switch).to_have_attribute("data-state", "checked")
    config = _get_user_config(sculptor_instance_)
    assert config["isErrorReportingEnabled"] is True
    assert config["isProductAnalyticsEnabled"] is True

    # 3. Confirming the opt-out persists all-flags-off.
    privacy_section.disable_telemetry()
    expect(telemetry_switch).to_have_attribute("data-state", "unchecked")
    config = _get_user_config(sculptor_instance_)
    assert all(config[key] is False for key in _TELEMETRY_FLAG_KEYS), config

    # 4. Opting back in is instant — no dialog — and restores the flags.
    privacy_section.enable_telemetry()
    expect(privacy_section.get_opt_out_dialog()).not_to_be_visible()
    expect(telemetry_switch).to_have_attribute("data-state", "checked")
    config = _get_user_config(sculptor_instance_)
    assert config["isErrorReportingEnabled"] is True
    assert config["isProductAnalyticsEnabled"] is True
    assert config["isSessionRecordingEnabled"] is False


@user_story("to be unable to change telemetry consent through the generic config endpoint")
def test_put_config_rejects_telemetry_flag_changes(sculptor_instance_: SculptorInstance) -> None:
    """Verifies behavior 5: the PUT guard for the SDK-facing telemetry flags."""
    page = sculptor_instance_.page
    base_url = sculptor_instance_.backend_api_url.rstrip("/")
    config = _get_user_config(sculptor_instance_)

    # Changing a telemetry flag is rejected with a pointer at the dedicated endpoint.
    response = page.request.put(
        f"{base_url}/api/v1/config",
        data={"userConfig": {"isProductAnalyticsEnabled": not config["isProductAnalyticsEnabled"]}},
    )
    assert response.status == 400, response.text()
    assert "/api/v1/config/telemetry" in response.json()["detail"]

    # Sending the current (unchanged) value passes through.
    response = page.request.put(
        f"{base_url}/api/v1/config",
        data={"userConfig": {"isProductAnalyticsEnabled": config["isProductAnalyticsEnabled"]}},
    )
    assert response.ok, response.text()


def _populate_with_path_mode_no_account(path: Path) -> None:
    """Write a config with dependency_paths.claude=PATH but no email/consent.

    PATH mode keeps the onboarding installation step on the DependencyCard
    flow (the managed-install flow can't complete in tests); the missing
    email/consent makes onboarding start from the welcome step.
    """
    internal_dir = path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config = UserConfig(
        user_email="",
        user_id="telemetry-opt-out-test",
        organization_id="telemetry-opt-out-test",
        instance_id="telemetry-opt-out-test",
        dependency_paths=DependencyPaths(claude="claude"),
    )
    save_config(config, internal_dir / "config.toml")


@user_story("to sign up while opting out of telemetry on the welcome screen")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode_no_account)
def test_onboarding_email_with_telemetry_opt_out(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Verifies behaviors 6 and 7: pre-checked checkbox; unchecking it persists all flags off."""
    with sculptor_instance_factory_.spawn_instance(auto_project=False) as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        welcome_step = onboarding_page.get_welcome_step()
        expect(welcome_step).to_be_visible()

        # 6. The telemetry checkbox defaults to checked; the skip link is offered.
        expect(welcome_step.get_telemetry_checkbox()).to_be_checked()
        expect(welcome_step.get_skip_account_link()).to_be_visible()

        # 7. Sign up with the checkbox unchecked.
        welcome_step.enter_email("optout@user.com")
        welcome_step.set_telemetry_opt_in(False)
        welcome_step.submit()

        expect(onboarding_page.get_installation_step()).to_be_visible()

        config = _get_user_config(sculptor_instance)
        assert config["userEmail"] == "optout@user.com"
        assert config["isPrivacyPolicyConsented"] is True
        assert all(config[key] is False for key in _TELEMETRY_FLAG_KEYS), config


@user_story("to use Sculptor without an account and still get past onboarding on every launch")
@custom_sculptor_folder_populator.with_args(_populate_with_path_mode_no_account)
def test_onboarding_skip_account_setup(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Verifies behavior 8: the account-less skip path, end to end.

    Skipping keeps the anonymous identity with (default) telemetry on, the
    rest of the wizard completes without an email, the Privacy settings show
    the email as "Unset", and a reload lands in the app — not the wizard.
    """
    with sculptor_instance_factory_.spawn_instance(auto_project=False) as sculptor_instance:
        page = sculptor_instance.page
        onboarding_page = PlaywrightOnboardingPage(page)

        # Skip the welcome step without entering anything.
        welcome_step = onboarding_page.get_welcome_step()
        expect(welcome_step).to_be_visible()
        welcome_step.skip_account_setup()

        installation_step = onboarding_page.get_installation_step()
        expect(installation_step).to_be_visible()

        # The config stays anonymous; consent and the default telemetry
        # choice are recorded.
        config = _get_user_config(sculptor_instance)
        assert config["userEmail"] == ""
        assert config["isPrivacyPolicyConsented"] is True
        assert config["isErrorReportingEnabled"] is True
        assert config["isProductAnalyticsEnabled"] is True

        # The rest of the wizard completes without an email.
        installation_step.complete_step()
        add_repo_step = onboarding_page.get_add_repo_step()
        expect(add_repo_step).to_be_visible()
        add_repo_step.complete_step(str(sculptor_instance_factory_.base_repo.base_path))

        add_workspace_page = PlaywrightNewWorkspaceModalPage(page=page)
        expect(add_workspace_page.get_submit_button()).to_be_visible()

        # Settings → Privacy shows the unset email and the enabled switch.
        settings_page = navigate_to_settings_page(page=page)
        privacy_section = settings_page.click_on_privacy()
        expect(privacy_section.get_email_field()).to_contain_text("Unset")
        expect(privacy_section.get_telemetry_switch()).to_have_attribute("data-state", "checked")

        # A reload routes back into the app — the consent-based onboarding
        # gate must not bounce the account-less user into the wizard.
        soft_reload_page(page)
        settings_page = navigate_to_settings_page(page=page)
        privacy_section = settings_page.click_on_privacy()
        expect(privacy_section.get_telemetry_switch()).to_be_visible(timeout=30000)
        expect(onboarding_page.get_welcome_step()).not_to_be_visible()
