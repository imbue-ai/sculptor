"""Integration tests for the BackendStatusBoundary shutdown stall recovery.

Covers SCU-403: when ``autoUpdater.quitAndInstall()`` fails (e.g. Squirrel's
cached download was purged), the Electron main process pushes a
``shutting_down`` backend status and never recovers. The
``BackendStatusBoundary`` locks into ``shutting_down`` and ignores all
subsequent updates, leaving the user stuck on the shutdown spinner with no
recovery path.

The fix adds a stall timeout: after a configurable interval in
``shutting_down``, the renderer swaps the spinner for a recovery message
that tells the user the shutdown failed and to relaunch the app manually.

These tests do NOT exercise the real Squirrel auto-updater — that bug is
impossible to reproduce in Playwright per ``.sculptor/testing.md`` (it
requires code-signed bundles, OS-level file system state, and the real
electron-updater MacUpdater module). What is testable end-to-end is the
new recovery rendering: simulate the ``shutting_down`` state via the
``window.sculptor`` mock and verify the renderer transitions to the
recovery UI after the timeout.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.auto_update_mock import MockSculptorElectronAPI
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

pytestmark = pytest.mark.release

# Short stall timeout the test injects via localStorage so we don't have to
# wait the production 30 s. The boundary reads this on every shutdown
# transition, so setting it before pushing shutting_down is sufficient.
_TEST_STALL_TIMEOUT_MS = 750


def _set_short_stall_timeout(page: object) -> None:
    page.evaluate(
        "ms => localStorage.setItem('__sculptor_shutdown_stall_timeout_ms', String(ms))",
        _TEST_STALL_TIMEOUT_MS,
    )


def _push_shutting_down(mock: MockSculptorElectronAPI) -> None:
    mock.push_backend_status(
        {"status": "shutting_down", "payload": {"message": "Installing update..."}},
    )


@user_story(
    "to see a recovery message instead of an indefinite spinner when an auto-update install fails to quit the app"
)
def test_shutdown_stall_recovery_after_timeout(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Pushing ``shutting_down`` shows the spinner; after the stall timeout
    elapses, the boundary swaps to the recovery UI without leaving
    ``shutting_down``.
    """
    page = sculptor_instance_.page

    _set_short_stall_timeout(page)
    _push_shutting_down(mock_electron_api)

    spinner = page.get_by_test_id(ElementIDs.BACKEND_SHUTDOWN_SPINNER)
    expect(spinner).to_be_visible()

    stalled = page.get_by_test_id(ElementIDs.BACKEND_SHUTDOWN_STALLED)
    expect(stalled).to_be_visible(timeout=_TEST_STALL_TIMEOUT_MS + 2_000)
    expect(spinner).not_to_be_visible()


@user_story(
    "to see the shutdown spinner remain in place while shutdown is still progressing within the expected window"
)
def test_shutdown_spinner_remains_before_timeout(
    sculptor_instance_: SculptorInstance,
    mock_electron_api: MockSculptorElectronAPI,
) -> None:
    """Within the stall timeout, the spinner is visible and the recovery UI
    is not — i.e. we don't surface the recovery message prematurely for
    normal-duration shutdowns.
    """
    page = sculptor_instance_.page

    _set_short_stall_timeout(page)
    _push_shutting_down(mock_electron_api)

    spinner = page.get_by_test_id(ElementIDs.BACKEND_SHUTDOWN_SPINNER)
    expect(spinner).to_be_visible()

    stalled = page.get_by_test_id(ElementIDs.BACKEND_SHUTDOWN_STALLED)
    # Wait less than the timeout — the recovery UI must NOT appear yet.
    page.wait_for_timeout(_TEST_STALL_TIMEOUT_MS // 3)
    expect(stalled).not_to_be_visible()
    expect(spinner).to_be_visible()
