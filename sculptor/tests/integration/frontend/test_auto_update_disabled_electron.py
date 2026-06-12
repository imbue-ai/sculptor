"""Packaged-electron test: SCULPTOR_DISABLE_AUTO_UPDATE produces "disabled" status.

The packaged-test shell script exports ``SCULPTOR_DISABLE_AUTO_UPDATE=1``.
This file sorts alphabetically before ``test_auto_update_electron.py``, so
these tests run first — before the auto-update fixture invalidates the
shared instance and removes the variable.  After the auto-update tests
finish, the fixture tears down and restores the original environment.

In dev mode (no ``SCULPTOR_DISABLE_AUTO_UPDATE``), these tests skip.

Run manually::

    SCULPTOR_DISABLE_AUTO_UPDATE=1 just test-integration-electron \
        sculptor/tests/integration/frontend/test_auto_update_disabled_electron.py
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.settings_update import PlaywrightSettingsUpdateElement
from sculptor.testing.elements.version_popover import PlaywrightVersionPopoverElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance

_SKIP_REASON = "SCULPTOR_DISABLE_AUTO_UPDATE is not set; only runs in packaged mode"


@pytest.mark.release
@pytest.mark.electron
def test_disabled_env_grays_out_settings_controls(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When SCULPTOR_DISABLE_AUTO_UPDATE is set, the settings controls are disabled."""
    if not os.environ.get("SCULPTOR_DISABLE_AUTO_UPDATE"):
        pytest.skip(_SKIP_REASON)

    page = sculptor_instance_.page
    navigate_to_settings_page(page)

    update_controls = PlaywrightSettingsUpdateElement(page)
    expect(update_controls.get_channel_select()).to_be_disabled()
    expect(update_controls.get_check_button()).to_be_disabled()


@pytest.mark.release
@pytest.mark.electron
def test_disabled_env_version_popover_shows_dash(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When SCULPTOR_DISABLE_AUTO_UPDATE is set, the popover shows disabled status."""
    if not os.environ.get("SCULPTOR_DISABLE_AUTO_UPDATE"):
        pytest.skip(_SKIP_REASON)

    page = sculptor_instance_.page

    popover = PlaywrightVersionPopoverElement(page)
    popover.open()

    expect(popover.get_channel()).to_have_text("—")
    expect(popover.get_status()).to_have_text("Auto-updates are disabled.")
