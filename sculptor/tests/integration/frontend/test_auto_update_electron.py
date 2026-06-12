"""Electron-mode integration tests for auto-update.

These tests run a real Electron app against a local HTTP server that serves
configurable update manifests.  The ``electron-updater`` library inside the
Electron main process performs real HTTP requests, SHA-512 verification, and
IPC status pushes — exercising the full update lifecycle end-to-end.

Environment variables are set before the Electron process launches:
``SCULPTOR_TEST_OVERRIDE_BASE_URL`` points the auto-updater at our local
test server, ``SCULPTOR_TEST_OVERRIDE_PACKAGED`` (dev builds) or
``SCULPTOR_TEST_SKIP_DEV_VERSION_GUARD`` (packaged dev builds) bypass
the guards that would otherwise prevent the auto-updater from running.
``SCULPTOR_DISABLE_AUTO_UPDATE`` (set by the packaged test shell script)
is removed so that the auto-updater initializes against the test server.

Run these tests with::

    just test-integration-electron sculptor/tests/integration/frontend/test_auto_update_electron.py
"""

from __future__ import annotations

import re
import sys
from typing import Generator

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.auto_update_server import AutoUpdateTestServer
from sculptor.testing.auto_update_server import auto_update_server as auto_update_server  # noqa: F401
from sculptor.testing.elements.settings_update import PlaywrightSettingsUpdateElement
from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.elements.version_popover import PlaywrightVersionPopoverElement
from sculptor.testing.playwright_utils import get_electron_app_version
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.resources import invalidate_shared_instance
from sculptor.testing.sculptor_instance import SculptorInstance

# ---------------------------------------------------------------------------
# Session-scoped fixture: set env vars before the Electron process starts
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _auto_update_electron_env(
    request: pytest.FixtureRequest,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
    sculptor_launch_mode: str,
) -> Generator[None]:
    """Inject env vars so the Electron auto-updater uses our test server.

    Invalidates the cached shared instance on setup and teardown so that:
    - On setup: any instance started with SCULPTOR_DISABLE_AUTO_UPDATE is torn
      down, and the next ``sculptor_instance_`` call creates a fresh process
      with the auto-updater pointed at our test server.
    - On teardown: the instance is torn down so subsequent tests (if any)
      get a process with the original (restored) environment.
    """
    is_packaged = sculptor_launch_mode == "packaged-electron"

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SCULPTOR_TEST_OVERRIDE_BASE_URL", auto_update_server.url)
        # The packaged test script exports SCULPTOR_DISABLE_AUTO_UPDATE=1 to
        # prevent auto-update from hitting S3 during non-auto-update tests.
        # Remove it here so the auto-updater initializes against our test server.
        mp.delenv("SCULPTOR_DISABLE_AUTO_UPDATE", raising=False)

        if is_packaged:
            # Packaged build: app.isPackaged is already true, but dev-versioned
            # builds need the dev guard bypassed.  Do NOT set forceDevUpdateConfig
            # — the app is already packaged and should use its normal config paths.
            mp.setenv("SCULPTOR_TEST_SKIP_DEV_VERSION_GUARD", "1")
        else:
            # Dev build: app is not packaged, so we need forceDevUpdateConfig to
            # make electron-updater work without a real packaged app.
            mp.setenv("SCULPTOR_TEST_OVERRIDE_PACKAGED", "1")

        # On Linux, AppImageUpdater requires APPIMAGE to point at the running
        # AppImage binary.  In dev test mode we're not running from a real
        # AppImage, so we provide a dummy path to satisfy the check.
        # In packaged mode the binary is extracted from the AppImage (squashfs-root)
        # so APPIMAGE is also unset — provide a dummy so the updater initializes.
        if sys.platform == "linux":
            fake_appimage = "/tmp/sculptor-test.AppImage"  # noqa: S108
            open(fake_appimage, "a").close()  # noqa: SIM115
            mp.setenv("APPIMAGE", fake_appimage)

        # Kill any instance that was started with the old env (e.g.
        # SCULPTOR_DISABLE_AUTO_UPDATE=1).  The next sculptor_instance_
        # call will create a fresh process with our test-server env.
        invalidate_shared_instance(request.config)
        yield
        # Env vars are about to be restored by MonkeyPatch — kill the
        # instance so subsequent tests get a process with the original env.
        invalidate_shared_instance(request.config)


@pytest.fixture(autouse=True)
def _reset_auto_update_state(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> Generator[None]:
    """Reset auto-update state in both the server and the Electron main process.

    The Electron main process retains its ``lastStatus`` across page reloads
    (it lives in the main process, not the renderer).  A previous test that
    reached "ready" leaves a persistent toast that overlays UI elements in the
    next test.  To fix this we:

    1. Point the server at "no update available".
    2. Trigger ``checkForUpdate()`` via IPC so the main process re-checks,
       receives "no update", and transitions to "idle".
    3. Wait for the renderer to reflect the idle state (toasts close).
    """
    page = sculptor_instance_.page
    auto_update_server.set_no_update()
    page.evaluate("window.sculptor.checkForUpdate()")
    page.wait_for_function(
        "async () => (await window.sculptor.getAutoUpdateStatus()).type === 'idle'",
    )
    # Wait for any lingering toasts to finish their close animation.
    toast = PlaywrightToastElement(page)
    expect(toast.get_close_buttons()).to_have_count(0)
    yield
    auto_update_server.set_no_update()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_version_popover(page: Page) -> PlaywrightVersionPopoverElement:
    """Open the version popover by clicking the version trigger."""
    popover = PlaywrightVersionPopoverElement(page)
    popover.open()
    return popover


def _click_check_for_updates(page: Page) -> None:
    """Navigate to Settings and click the 'Check for updates' button."""
    navigate_to_settings_page(page)
    update = PlaywrightSettingsUpdateElement(page)
    button = update.get_check_button()
    expect(button).to_be_visible()
    button.click()


# ---------------------------------------------------------------------------
# E1: Happy path — update available → download → ready
# ---------------------------------------------------------------------------


@pytest.mark.release
@pytest.mark.electron
@pytest.mark.skipif(sys.platform == "darwin", reason="Squirrel.Mac cannot process unsigned test bundles")
def test_update_available_and_ready(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """Server advertises a higher version; electron-updater downloads it and reaches 'ready'.

    Verifies the full update lifecycle: manifest check → download → ready toast.
    Skipped on macOS because Squirrel.Mac requires code-signed bundles to
    complete the download-to-ready transition.
    """
    page = sculptor_instance_.page

    # Configure the test server to advertise version 99.0.0 (higher than 0.0.0).
    auto_update_server.set_update("99.0.0")

    # Trigger a manual check via the Settings page button.
    _click_check_for_updates(page)

    # Wait for the "ready" toast which appears after electron-updater finishes
    # downloading and verifying the artifact.  We filter by text because
    # the download toast may still be animating closed, causing two TOAST
    # elements to exist momentarily (strict mode violation without filter).
    toast = PlaywrightToastElement(page)
    ready_toast = toast.filter_by_text("Update ready (v99.0.0)")
    expect(ready_toast).to_be_visible(timeout=60_000)

    # E8: The green update dot should be visible in the sidebar when ready.
    version_popover = PlaywrightVersionPopoverElement(page)
    expect(version_popover.get_update_dot()).to_be_visible()


# ---------------------------------------------------------------------------
# E2: No update available
# ---------------------------------------------------------------------------


@pytest.mark.release
@pytest.mark.electron
def test_no_update_available_shows_up_to_date(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """Server advertises the same version as the running app; status shows 'Up to date'."""
    page = sculptor_instance_.page

    # Configure the test server to report the current version.
    auto_update_server.set_no_update(get_electron_app_version(page))

    # Trigger a manual check via the Settings page button.
    _click_check_for_updates(page)

    # Wait for the popover to show "Up to date" (idle status).
    popover = _open_version_popover(page)
    expect(popover.get_status()).to_contain_text(
        "Up to date",
        timeout=30_000,
    )


# ---------------------------------------------------------------------------
# E3: Download failure — artifact missing → error
# ---------------------------------------------------------------------------


@pytest.mark.release
@pytest.mark.electron
def test_download_failure_shows_error(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """Server advertises an update but the artifact 404s; status reaches 'error'."""
    page = sculptor_instance_.page

    # Valid manifest for 99.0.0, but artifact requests will 404.
    auto_update_server.set_update_missing_artifact("99.0.0")

    _click_check_for_updates(page)

    # The version popover should show the error status.  We check the popover
    # rather than the toast because the error toast auto-dismisses after 5s.
    popover = _open_version_popover(page)
    expect(popover.get_status()).to_contain_text(
        "Update error:",
        timeout=30_000,
    )


# ---------------------------------------------------------------------------
# E4: Network failure — server unreachable → error
# ---------------------------------------------------------------------------


@pytest.mark.release
@pytest.mark.electron
def test_network_failure_shows_error(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """Server is offline; manual check reaches 'error' status."""
    page = sculptor_instance_.page

    auto_update_server.set_offline()
    try:
        _click_check_for_updates(page)

        # The version popover should show the error status.
        popover = _open_version_popover(page)
        expect(popover.get_status()).to_contain_text(
            "Update error:",
            timeout=30_000,
        )
    finally:
        auto_update_server.set_online()


# ---------------------------------------------------------------------------
# E5a: Channel switch — STABLE → RC (verify RC feed path)
# ---------------------------------------------------------------------------


def _enable_channel_select(page: Page, auto_update_server: AutoUpdateTestServer) -> None:  # noqa: F811
    """Trigger a check so the channel atom is populated and the select is enabled."""
    auto_update_server.set_no_update(get_electron_app_version(page))
    _click_check_for_updates(page)
    update = PlaywrightSettingsUpdateElement(page)
    expect(update.get_channel_select()).to_be_enabled(timeout=30_000)


@pytest.mark.release
@pytest.mark.electron
def test_channel_switch_stable_to_rc(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """Switching STABLE → RC sends requests on the RC feed path."""
    page = sculptor_instance_.page

    # Ensure channel select is usable (populates channel atom).
    _enable_channel_select(page, auto_update_server)

    # Clear path log, then switch to RC.
    auto_update_server.clear_request_paths()
    update = PlaywrightSettingsUpdateElement(page)
    update.get_channel_select().click()
    update.get_channel_option_rc().click()

    # After the channel switch, autoUpdater re-checks against the RC feed.
    popover = _open_version_popover(page)
    expect(popover.get_channel()).to_have_text(
        "Latest",
        timeout=30_000,
    )
    expect(popover.get_status()).to_contain_text(
        "Up to date",
        timeout=30_000,
    )

    # Verify the server saw a request on the RC path (/slim-rc/...).
    paths = auto_update_server.get_request_paths()
    assert any("/slim-rc/" in p for p in paths), f"Expected RC feed path in {paths}"


# ---------------------------------------------------------------------------
# E5b: Channel switch — RC → STABLE after RC download
# ---------------------------------------------------------------------------


@pytest.mark.release
@pytest.mark.electron
@pytest.mark.skipif(sys.platform == "darwin", reason="Squirrel.Mac cannot process unsigned test bundles")
def test_channel_switch_rc_to_stable_after_download(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """After downloading an RC update, switching to STABLE resets to 'Up to date'.

    This test verifies that when the user downloads an update on the RC channel
    and then switches back to STABLE, the status correctly shows "Up to date"
    (not "ready") and the feed path switches back to /slim/.
    """
    page = sculptor_instance_.page

    # Ensure channel select is usable.
    _enable_channel_select(page, auto_update_server)

    # Switch to RC and trigger an update download.
    update = PlaywrightSettingsUpdateElement(page)
    update.get_channel_select().click()
    update.get_channel_option_rc().click()

    # Wait for RC channel to be active.
    popover = _open_version_popover(page)
    expect(popover.get_channel()).to_have_text(
        "Latest",
        timeout=30_000,
    )
    # Close the popover before triggering the download.
    page.keyboard.press("Escape")

    # Advertise a new version on RC — this triggers download → ready.
    auto_update_server.set_update("99.0.0")
    _click_check_for_updates(page)

    # Wait for the "ready" toast (download complete).
    toast = PlaywrightToastElement(page)
    ready_toast = toast.filter_by_text("Update ready (v99.0.0)")
    expect(ready_toast).to_be_visible(timeout=60_000)

    # Now switch back to STABLE (no update available on STABLE).
    auto_update_server.clear_request_paths()
    auto_update_server.set_no_update(get_electron_app_version(page))
    navigate_to_settings_page(page)
    update = PlaywrightSettingsUpdateElement(page)
    channel_select = update.get_channel_select()
    expect(channel_select).to_be_enabled(timeout=30_000)
    channel_select.click()
    update.get_channel_option_stable().click()

    # Verify popover shows STABLE and "Up to date" (not "ready").
    popover = _open_version_popover(page)
    expect(popover.get_channel()).to_have_text(
        "Stable",
        timeout=30_000,
    )
    expect(popover.get_status()).to_contain_text(
        "Up to date",
        timeout=30_000,
    )

    # Verify the server saw requests on the STABLE path (/slim/, not /slim-rc/).
    paths = auto_update_server.get_request_paths()
    assert any("/slim/" in p and "/slim-rc/" not in p for p in paths), f"Expected STABLE feed path in {paths}"


# ---------------------------------------------------------------------------
# E9: User-Agent identifies Sculptor
# ---------------------------------------------------------------------------


@pytest.mark.electron
def test_user_agent_identifies_sculptor(
    sculptor_instance_: SculptorInstance,
    auto_update_server: AutoUpdateTestServer,  # noqa: F811
) -> None:
    """Auto-updater requests carry a Sculptor-specific User-Agent.

    Production S3 access logs on ``imbue-sculptor-releases`` use this UA to
    attribute traffic by app version, platform, and arch.  Without it, every
    request is just ``electron-builder`` and indistinguishable.
    """
    page = sculptor_instance_.page

    # No-op check so the test doesn't trigger a download.
    auto_update_server.set_no_update(get_electron_app_version(page))

    # Clear request state, then trigger a fresh check.
    auto_update_server.clear_request_paths()
    _click_check_for_updates(page)

    # Wait until the popover reflects idle — at which point the request has been served.
    _open_version_popover(page)
    expect(page.get_by_test_id(ElementIDs.VERSION_POPOVER_STATUS)).to_contain_text(
        "Up to date",
        timeout=30_000,
    )

    user_agents = auto_update_server.get_request_user_agents()
    assert user_agents, "Expected at least one request after a manual update check"
    ua_pattern = re.compile(r"^Sculptor/(?P<version>\S+) \((?P<platform>[^;]+); (?P<arch>[^)]+)\)$")
    for ua in user_agents:
        match = ua_pattern.match(ua)
        assert match, f"User-Agent does not match 'Sculptor/<version> (<platform>; <arch>)': {ua!r}"
        assert match.group("platform") == sys.platform, (
            f"Expected platform {sys.platform!r} in User-Agent, got {match.group('platform')!r} ({ua!r})"
        )
