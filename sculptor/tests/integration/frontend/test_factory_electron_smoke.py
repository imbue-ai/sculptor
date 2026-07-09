"""Smoke test for the per-test factory's real (non-packaged) Electron path.

The factory fixture (``sculptor_instance_factory_``) gained an Electron launch
mode, so a single ``@browser_and_electron`` test can run against both a plain
Chromium page and a real Electron shell from the same per-instance-isolated
config. This test proves ``spawn_instance()`` reaches a rendered app in
whichever mode the run selected, and that the Electron run produces an Electron
instance rather than silently falling back to the browser.
"""

import pytest

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import expect_app_not_onboarding
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

# Generous headroom for a cold per-test Electron + Vite dev server start, mirroring
# the shared-instance render budget in sculptor/testing/resources.py. Browser mode
# renders far faster but shares the same wait.
_RENDER_TIMEOUT_MS = 90_000


@pytest.mark.browser_and_electron
def test_factory_instance_renders_app(
    sculptor_instance_factory_: SculptorInstanceFactory,
    sculptor_launch_mode: str,
) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        # The app rendered past onboarding. The sidebar rail is the harness's
        # universal "app rendered, not onboarding" signal (present on every in-app
        # destination and the empty-first-run page, but not the onboarding wizard).
        app_ready = instance.page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
        expect_app_not_onboarding(instance.page, app_ready, timeout=_RENDER_TIMEOUT_MS)

        # Under an electron launch mode the instance must be a real Electron shell,
        # not the browser fallback — that is the whole point of the new path.
        if sculptor_launch_mode in ("electron", "electron-custom-command"):
            assert instance.is_electron, (
                f"expected a real Electron instance under launch mode {sculptor_launch_mode!r}"
            )
        elif sculptor_launch_mode == "browser":
            assert not instance.is_electron
