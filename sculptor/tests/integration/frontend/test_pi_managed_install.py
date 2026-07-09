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
- CUSTOM state: a CUSTOM pi value never triggers auto-install, so the backend
  stays offline.
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

from sculptor.constants import ElementIDs
from sculptor.services.dependency_management_service import DEPENDENCIES_DIR_NAME
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import _VERSION_DIR_PREFIX
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import open_new_workspace_form
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


def _set_pi_config(factory: SculptorInstanceFactory, pi_value: str) -> None:
    """Rewrite the factory's pre-created config to a given pi binary-source value.

    Preserves the factory's healthy claude setup (resolved from the default stub
    on PATH) and only overrides ``dependency_paths.pi`` so onboarding stays
    skipped and only pi's mode changes.
    """
    config_path = _factory_sculptor_folder(factory) / "internal" / "config.toml"
    config = load_config(config_path)
    new_dependency_paths = config.dependency_paths.model_copy(update={"pi": pi_value})
    save_config(config.model_copy(update={"dependency_paths": new_dependency_paths}), config_path)


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


@user_story("to be steered to Settings → Pi when picking pi while it is not installed")
def test_pi_unavailable_picker_offers_install_pi_and_routes_to_settings(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """With no resolvable pi binary the new-workspace picker's pi entry reads
    "Install Pi", and choosing it opens Settings → Pi instead of selecting a
    harness that cannot launch."""
    # CUSTOM with no path resolves to nothing, so pi is deterministically
    # unavailable without any network access.
    _set_pi_config(sculptor_instance_factory_, "CUSTOM")

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        # A fresh instance has no workspaces; bring up the new-workspace
        # dialog, which hosts the AgentTypeSelect.
        open_new_workspace_form(page)
        dialog = PlaywrightNewWorkspaceDialog(page)
        dialog.get_agent_type_select().click()

        pi_option = dialog.get_agent_type_option_pi()
        expect(pi_option).to_have_text("Install Pi")
        pi_option.click()

        # Choosing "Install Pi" lands on Settings → Pi (the Binary-Source
        # selector is that section's control entry point).
        expect(page.get_by_test_id(ElementIDs.PI_MODE_SELECTOR)).to_be_visible()


@user_story("to see a clear error when pi stops being available before its first message")
def test_pi_workspace_surfaces_structured_failure_when_pi_becomes_unavailable(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The agent pickers refuse to select pi while it is unavailable, so the
    runtime safety net is driven by breaking pi *after* creation: the workspace
    is created while pi resolves (the pre-staged managed FakePi), pi's binary
    source is then switched to a pathless CUSTOM in Settings, and the first
    message drives PiAgent.start, which resolves no binary and surfaces the
    structured failure in chat (FAIL-3, mirrors test_missing_claude_binary)."""
    _set_pi_config(sculptor_instance_factory_, "MANAGED")
    _stage_fake_pi_managed_binary(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Not Ready",
            model_name=None,
            agent_type="pi",
        )

        # Break pi's binary source: a pathless CUSTOM resolves to nothing. The
        # pi process is only spawned on the first message, so the agent hits
        # the missing binary at start.
        settings_page = navigate_to_settings_page(page=page)
        pi_section = settings_page.click_on_pi()
        mode_selector = pi_section.get_mode_selector()
        expect(mode_selector).to_be_visible()
        mode_selector.click()
        custom_option = pi_section.get_mode_option_custom()
        expect(custom_option).to_be_visible()
        custom_option.click()
        # The binary-path field is CUSTOM-only, so its appearance confirms the
        # switch settled before we leave Settings.
        expect(pi_section.get_binary_path_input()).to_be_visible()

        # Back to the workspace, then drive the pi start.
        navigate_to_workspace(page, "Pi Not Ready")
        chat_panel = task_page.get_chat_panel()
        send_chat_message(chat_panel, "hello pi")

        # The pi start failure surfaces as a structured error block in the chat.
        error_block = chat_panel.get_error_block()
        expect(error_block).to_be_visible(timeout=60_000)
        expect(error_block).to_contain_text("Pi binary not found")
