"""Integration coverage for the managed-pi settings UX and install wiring.

The download/verify/stage internals are unit-covered (03_03), so this file
focuses on the UI states + wiring (UI-1..5, SVC-4, FAIL-1/3).

Hermetic / no-network strategy
------------------------------
The backend runs as a separate process and a managed install would otherwise
fetch a tarball from GitHub Releases — neither monkeypatching the pin nor a
``file://`` download works across that boundary, and CI has no network. So each
test drives a deterministic, network-free state:

- MANAGED *installed* state: pre-stage a FakePi tree as the managed binary at
  ``version-<pin>/pi/pi`` before the backend starts. Startup auto-install then
  sees an installed+in-range binary and skips the download entirely (no
  network); FakePi answers ``--version`` for the activation gate.
- CUSTOM / banner states: a CUSTOM pi value never triggers auto-install, so the
  backend stays offline.
- Install *failure*: start in CUSTOM (no startup auto-install), switch to MANAGED
  in the UI to reveal the Install button, and intercept the install POST at the
  browser so the click exercises the ``install_managed(PI)`` wiring and surfaces
  a structured error + Retry — without the backend ever hitting the network.
- "pi not ready": a CUSTOM pi value with no path resolves to nothing, so running
  a pi workspace surfaces the structured ``PiBinaryNotFoundError`` rather than
  blocking workspace creation.
"""

import json
from pathlib import Path

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.backend_contract import DEPENDENCIES_DIR_NAME
from sculptor.testing.backend_contract import PI_VERSION_RANGE
from sculptor.testing.backend_contract import _VERSION_DIR_PREFIX
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# A deterministic, network-free stand-in for the structured error the real
# download/verify path raises when the pinned sha256 does not match.
_CHECKSUM_ERROR = "Checksum mismatch: pinned sha256 did not match the downloaded artifact"

_INSTALL_ENDPOINT_GLOB = "**/api/v1/dependencies/install*"


def _factory_sculptor_folder(factory: SculptorInstanceFactory) -> Path:
    """The data root the spawned backend will read (mirrors test_missing_claude_binary)."""
    return factory._delegate.sculptor_folder


def _set_pi_config(factory: SculptorInstanceFactory, pi_value: str, enable_pi_agent: bool = False) -> None:
    """Rewrite the factory's pre-created config to a given pi binary-source value.

    Preserves the factory's healthy claude setup (resolved from the default stub
    on PATH) and only overrides ``dependency_paths.pi`` so onboarding stays
    skipped and only pi's mode changes.
    """
    config_path = _factory_sculptor_folder(factory) / "internal" / "config.toml"
    config = load_config(config_path)
    new_dependency_paths = config.dependency_paths.model_copy(update={"pi": pi_value})
    updates: dict[str, object] = {"dependency_paths": new_dependency_paths}
    if enable_pi_agent:
        updates["enable_pi_agent"] = True
    save_config(config.model_copy(update=updates), config_path)


def _stage_fake_pi_managed_binary(factory: SculptorInstanceFactory) -> None:
    """Pre-stage FakePi as the managed pi binary so MANAGED is installed without a download.

    Writes the FakePi wrapper to ``<deps>/pi/version-<pin>/pi/pi`` — the exact
    path ``_find_managed_binary(PI)`` resolves — so startup auto-install sees an
    installed, in-range binary and never reaches the network.
    """
    version_dir = (
        _factory_sculptor_folder(factory)
        / "internal"
        / DEPENDENCIES_DIR_NAME
        / "pi"
        / f"{_VERSION_DIR_PREFIX}{PI_VERSION_RANGE.recommended_version}"
    )
    pi_tree = version_dir / "pi"
    pi_tree.mkdir(parents=True, exist_ok=True)
    # install_fake_pi_binary writes "<dir>/pi"; targeting pi_tree yields the
    # "pi/pi" managed sub-path.
    install_fake_pi_binary(pi_tree)


@user_story("to manage the pinned pi binary from Settings without a manual-install or sign-in surface")
def test_pi_settings_managed_shows_managed_controls_and_no_manual_install(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Under MANAGED the section shows the Binary-Source selector + a managed
    install control, hides the npm manual block, and shows no auth surface."""
    _set_pi_config(sculptor_instance_factory_, "MANAGED")
    _stage_fake_pi_managed_binary(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        # Binary-Source selector is the managed control entry point.
        expect(pi_section.get_mode_selector()).to_be_visible()
        expect(pi_section.get_mode_selector()).to_contain_text("Managed")

        # The pre-staged binary is in range, so the status reports the pinned
        # version and the managed-install row settles to "Up to date" (the
        # in-range form of the Install/Retry control).
        expect(pi_section.get_up_to_date()).to_be_visible()
        expect(pi_section.get_up_to_date()).to_contain_text("Pinned")
        expect(pi_section.get_install_button().or_(pi_section.get_up_to_date())).to_be_visible()

        # The manual npm block is CUSTOM-only and must be hidden here.
        expect(pi_section.get_install_commands_block()).to_have_count(0)

        # pi authenticates via env-var injection; no sign-in surface (REQ-SVC-4).
        expect(pi_section.get_auth_surface()).to_have_count(0)


@user_story("to point pi at a custom binary and see the manual-install commands")
def test_pi_settings_custom_shows_binary_path_and_manual_install(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Under CUSTOM the section shows the binary-path field and the npm block."""
    _set_pi_config(sculptor_instance_factory_, "CUSTOM")

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        expect(pi_section.get_mode_selector()).to_contain_text("Custom")
        expect(pi_section.get_binary_path_input()).to_be_visible()
        expect(pi_section.get_install_commands_block()).to_be_visible()


@user_story("to configure pi from Settings even before enabling the experimental harness")
def test_pi_settings_section_visible_with_pi_agent_disabled(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """With enable_pi_agent OFF (the default) the section is still usable —
    it shows the disabled banner alongside the working Binary-Source selector."""
    _set_pi_config(sculptor_instance_factory_, "CUSTOM")

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        expect(pi_section.get_disabled_banner()).to_be_visible()
        expect(pi_section.get_mode_selector()).to_be_visible()


@user_story("to retry a managed pi install after a checksum failure")
def test_pi_settings_install_button_invokes_managed_install_and_surfaces_error(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Clicking Install calls install_managed(PI); a structured failure surfaces
    the error with a Retry button (FAIL-1).

    Starts in CUSTOM so the backend performs no startup auto-install, switches to
    MANAGED in the UI to reveal the Install button, then intercepts the install
    POST at the browser to return a structured failure — exercising the wiring
    without any network access.
    """
    _set_pi_config(sculptor_instance_factory_, "CUSTOM")

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settings_page = navigate_to_settings_page(page=page)
        pi_section = settings_page.click_on_pi()

        # Switch to MANAGED so the managed Install control renders.
        mode_selector = pi_section.get_mode_selector()
        expect(mode_selector).to_be_visible()
        mode_selector.click()
        managed_option = pi_section.get_mode_option_managed()
        expect(managed_option).to_be_visible()
        managed_option.click()

        install_button = pi_section.get_install_button()
        expect(install_button).to_be_visible()
        expect(install_button).to_have_text("Install pi")

        install_requests: list[str] = []

        def _fail_install(route: Route) -> None:
            install_requests.append(route.request.url)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": False, "error": _CHECKSUM_ERROR}),
            )

        page.route(_INSTALL_ENDPOINT_GLOB, _fail_install)
        try:
            install_button.click()
            # The structured failure flips the managed control to its Retry form
            # — the button only reads "Retry" when an install error is surfaced.
            expect(install_button).to_have_text("Retry")
        finally:
            page.unroute(_INSTALL_ENDPOINT_GLOB, _fail_install)

        # The click reached the real install endpoint for the PI tool.
        assert install_requests, "Install click did not call the dependencies install endpoint"
        assert any("tool=PI" in url for url in install_requests), (
            f"install endpoint was not called with tool=PI: {install_requests}"
        )


@user_story("to see a clear error when running a pi workspace before pi is available")
def test_pi_workspace_surfaces_structured_failure_when_pi_unavailable(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Running a pi workspace with no resolvable pi binary surfaces the existing
    structured failure in chat (FAIL-3) rather than blocking workspace creation."""
    # CUSTOM with no path resolves to nothing and triggers no auto-install, so pi
    # is deterministically unavailable without any network access.
    _set_pi_config(sculptor_instance_factory_, "CUSTOM")

    with sculptor_instance_factory_.spawn_instance() as instance:
        # start_task_and_wait_for_ready enables the pi-agent picker for us.
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            workspace_name="Pi Not Ready",
            model_name=None,
            agent_type="pi",
        )
        chat_panel = task_page.get_chat_panel()

        # An empty-prompt workspace leaves the agent waiting, so the pi process is
        # not spawned until the first message; sending one drives PiAgent.start,
        # which resolves no binary and raises the structured failure (mirrors
        # test_missing_claude_binary).
        send_chat_message(chat_panel, "hello pi")

        # The workspace is created (not blocked); the pi start failure surfaces as
        # a structured error block in the chat.
        error_block = chat_panel.get_error_block()
        expect(error_block).to_be_visible(timeout=60_000)
        expect(error_block).to_contain_text("Pi binary not found")
