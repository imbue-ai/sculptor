"""Browser-mode integration tests for the auto-update UI.

These tests inject a mock ``window.sculptor`` and push synthetic
``AutoUpdateStatus`` events to verify rendering, toast behavior, and
IPC call correctness — without needing a real Electron shell.

Marked ``@pytest.mark.release`` so they also run in packaged CI jobs.
In ``packaged-electron`` mode the mock cannot override the real preload,
so the ``mock_electron_api`` fixture skips them automatically.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from sculptor.testing.auto_update_mock import MockSculptorElectronAPI
from sculptor.testing.elements.settings_update import PlaywrightSettingsUpdateElement
from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.elements.version_popover import PlaywrightVersionPopoverElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance

pytestmark = pytest.mark.release


def test_null_initial_state_version_popover(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Before any status event, the VersionPopover shows placeholder dashes."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)

    expect(version_popover.get_trigger()).to_be_visible()
    version_popover.open()

    expect(version_popover).to_be_visible()
    expect(version_popover.get_channel()).to_have_text("—")
    expect(version_popover.get_status()).to_have_text("Auto-updates are disabled.")


def test_null_initial_state_settings_page(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Before any status event, the Settings channel selector is disabled."""
    page = sculptor_instance_.page
    navigate_to_settings_page(page)

    update_controls = PlaywrightSettingsUpdateElement(page=page)
    expect(update_controls.get_channel_select()).to_be_disabled()


def test_idle_status_shows_up_to_date(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing an idle status shows 'Up to date' in the VersionPopover."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    mock_electron_api.push_status({"type": "idle", "channel": "STABLE"})

    version_popover.open()
    expect(version_popover.get_status()).to_have_text("Up to date.")
    expect(version_popover.get_channel()).to_have_text("Stable")


def test_checking_status_shows_checking(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing a checking status shows 'Checking...' in the popover."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    mock_electron_api.push_status({"type": "checking", "channel": "STABLE"})

    version_popover.open()
    expect(version_popover.get_status()).to_have_text("Checking for updates…")


def test_downloading_status_shows_progress(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing a downloading status shows progress in the popover and a toast."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    toast = PlaywrightToastElement(page=page)
    mock_electron_api.push_status({"type": "downloading", "channel": "STABLE", "percent": 42})

    # The download toast is persistent (infinite duration) and overlays the
    # VERSION trigger — verify it first, then dismiss before clicking VERSION.
    expect(toast).to_be_visible()
    expect(toast.get_toasts()).to_contain_text("Downloading update")

    toast.dismiss_all()

    version_popover.open()
    expect(version_popover.get_status()).to_have_text("Downloading update — 42%…")


def test_ready_status_shows_restart_button(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing a ready status shows the version and a restart button in the popover."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    toast = PlaywrightToastElement(page=page)
    mock_electron_api.push_status({"type": "ready", "channel": "STABLE", "version": "2.0.0"})

    # The "Update ready" toast is persistent and overlays the VERSION trigger —
    # verify it has rendered first, then dismiss before clicking VERSION.
    expect(toast).to_be_visible()
    toast.dismiss_all()

    version_popover.open()
    expect(version_popover.get_status()).to_have_text("v2.0.0 is ready to install.")

    restart_button = version_popover.get_restart_button()
    expect(restart_button).to_be_visible()

    # Clicking restart should call installUpdate IPC
    restart_button.click()
    calls = mock_electron_api.get_ipc_calls(method="installUpdate")
    assert len(calls) == 1


def test_ready_status_shows_persistent_toast(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing a ready status shows a persistent toast with Restart action."""
    page = sculptor_instance_.page
    toast = PlaywrightToastElement(page=page)
    mock_electron_api.push_status({"type": "ready", "channel": "STABLE", "version": "2.0.0"})

    ready_toast = toast.filter_by_text("Update ready (v2.0.0)")
    expect(ready_toast).to_be_visible()

    expect(toast.get_action_button()).to_have_text("Install and restart")


def test_error_status_shows_error(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing an error status shows the error message in popover and toast."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    toast = PlaywrightToastElement(page=page)
    mock_electron_api.push_status({"type": "error", "channel": "STABLE", "message": "Network timeout"})

    # The error toast auto-dismisses after 5 s — verify it before it vanishes.
    error_toast = toast.filter_by_text("Network timeout")
    expect(error_toast).to_be_visible()

    toast.dismiss_all()

    version_popover.open()
    expect(version_popover.get_status()).to_have_text("Update error: Network timeout")


def test_update_dot_appears_when_ready(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """The green update dot appears next to the version text when an update is ready."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    mock_electron_api.push_status({"type": "ready", "channel": "STABLE", "version": "2.0.0"})

    expect(version_popover.get_update_dot()).to_be_visible()


def test_update_dot_appears_when_downloading(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """The update dot also appears during download."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)
    mock_electron_api.push_status({"type": "downloading", "channel": "STABLE", "percent": 10})

    expect(version_popover.get_update_dot()).to_be_visible()


def test_dismissed_download_toast_stays_dismissed(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """After dismissing the download toast, new downloading events don't re-show it."""
    page = sculptor_instance_.page
    toast = PlaywrightToastElement(page=page)

    # Show and dismiss download toast
    mock_electron_api.push_status({"type": "downloading", "channel": "STABLE", "percent": 20})
    expect(toast).to_be_visible()

    toast.get_close_buttons().click()
    expect(toast.get_toasts()).not_to_be_visible()

    # Push another downloading event — toast should NOT reappear
    mock_electron_api.push_status({"type": "downloading", "channel": "STABLE", "percent": 50})
    expect(toast.get_toasts()).not_to_be_visible()

    # But transitioning to ready SHOULD show the ready toast
    mock_electron_api.push_status({"type": "ready", "channel": "STABLE", "version": "2.0.0"})
    ready_toast = toast.filter_by_text("Update ready (v2.0.0)")
    expect(ready_toast).to_be_visible()


def test_channel_switch_calls_ipc_and_shows_pending(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Changing the channel from the Settings Select calls setUpdateChannel IPC."""
    page = sculptor_instance_.page

    # Push initial idle status so the selector is enabled
    mock_electron_api.push_status({"type": "idle", "channel": "STABLE"})
    navigate_to_settings_page(page)

    update_controls = PlaywrightSettingsUpdateElement(page=page)

    # Open the channel Select and pick RC
    channel_select = update_controls.get_channel_select()
    expect(channel_select).to_be_visible()
    channel_select.click()

    update_controls.get_channel_option_rc().click()

    # Verify setUpdateChannel was called with "RC"
    calls = mock_electron_api.get_ipc_calls(method="setUpdateChannel")
    assert len(calls) == 1
    assert calls[0]["args"] == ["RC"]

    # Simulate the main process responding with a checking status on the new channel
    mock_electron_api.push_status({"type": "checking", "channel": "RC"})

    # The check button should show "Checking..." state (disabled)
    check_button = update_controls.get_check_button()
    expect(check_button).to_be_disabled()
    expect(check_button).to_contain_text("Checking")

    # Simulate completion
    mock_electron_api.push_status({"type": "idle", "channel": "RC"})

    # Check button should return to normal
    expect(check_button).to_be_enabled()
    expect(check_button).to_contain_text("Check for updates")


def test_channel_switch_failure_shows_error_toast(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """When setUpdateChannel IPC fails, an error toast is shown."""
    page = sculptor_instance_.page
    toast = PlaywrightToastElement(page=page)

    # Push initial idle status
    mock_electron_api.push_status({"type": "idle", "channel": "STABLE"})
    navigate_to_settings_page(page)

    # Configure the mock to reject setUpdateChannel
    mock_electron_api.configure_ipc_failure("setUpdateChannel", "Permission denied")

    update_controls = PlaywrightSettingsUpdateElement(page=page)

    # Open the channel Select and pick RC
    channel_select = update_controls.get_channel_select()
    expect(channel_select).to_be_visible()
    channel_select.click()

    update_controls.get_channel_option_rc().click()

    # An error toast should appear
    error_toast = toast.filter_by_text("Failed to change update channel")
    expect(error_toast).to_be_visible()


def test_check_for_updates_button(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Clicking 'Check for updates' calls checkForUpdate IPC."""
    page = sculptor_instance_.page

    # Push idle so the button is enabled
    mock_electron_api.push_status({"type": "idle", "channel": "STABLE"})
    navigate_to_settings_page(page)

    update_controls = PlaywrightSettingsUpdateElement(page=page)
    check_button = update_controls.get_check_button()
    expect(check_button).to_be_visible()
    check_button.click()

    calls = mock_electron_api.get_ipc_calls(method="checkForUpdate")
    assert len(calls) == 1


def test_disabled_status_grays_out_settings_controls(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """When auto-update is disabled, the channel selector and check button are disabled."""
    page = sculptor_instance_.page

    mock_electron_api.push_status({"type": "disabled"})
    navigate_to_settings_page(page)

    update_controls = PlaywrightSettingsUpdateElement(page=page)
    expect(update_controls.get_channel_select()).to_be_disabled()
    expect(update_controls.get_check_button()).to_be_disabled()


def test_disabled_status_version_popover_shows_dash(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """When auto-update is disabled, the VersionPopover shows dashes for channel and status."""
    page = sculptor_instance_.page
    version_popover = PlaywrightVersionPopoverElement(page=page)

    mock_electron_api.push_status({"type": "disabled"})

    version_popover.open()

    expect(version_popover.get_channel()).to_have_text("—")
    expect(version_popover.get_status()).to_have_text("Auto-updates are disabled.")
