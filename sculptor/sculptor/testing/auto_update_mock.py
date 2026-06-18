"""Mock for window.sculptor Electron API in browser-mode integration tests.

Injects a fake ``window.sculptor`` object via ``page.add_init_script`` so that
``useAutoUpdateListener`` registers its callback.  Tests can then push
``AutoUpdateStatus`` events and assert on the resulting UI, without needing a
real Electron shell or IPC bridge.

The mock is gated on a ``localStorage`` flag (``__sculptor_mock_enabled``).
``uninstall()`` clears this flag and ``window.sculptor``, then reloads so the
SPA re-initialises without the mock.  The shared-instance ``_pre_test()``
cleanup also calls ``localStorage.clear()``, providing a safety net.

**Known side-effects of injecting ``window.sculptor``:**

The frontend branches on ``window.sculptor`` in several places beyond
auto-update.  When the mock is active:

- ``Auth.ts``: ``initializeSessionToken()`` calls ``getSessionToken()``.
- ``apiClient.ts``: ``configureClient()`` may call ``getBackendPort()``
  (only when ``API_URL_BASE`` is undefined).
- ``BackendStatusBoundary.tsx``: calls ``getCurrentBackendStatus()`` and
  registers via ``onBackendStatusChange()``.
- ``TerminalPanel.tsx``: calls ``getBackendPort()`` for the WebSocket URL.
- ``FilePreviewList.tsx`` / ``FileUploadUtils.ts``: call ``getFileData()``
  / ``saveFile()``.
- ``electron/utils.ts``: ``isElectron()`` returns ``true``, so
  ``selectProjectDirectory()`` becomes reachable.

Methods not needed by auto-update tests throw explicitly so that
unintended calls surface immediately rather than silently altering
test behaviour.
"""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping

import pytest
from playwright.sync_api import Page

from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.sculptor_instance import SculptorInstance

# JavaScript injected via ``add_init_script`` — runs before any page scripts.
# Only creates the mock when the localStorage flag is set, so non-auto-update
# tests sharing the same page instance are unaffected.
_MOCK_INIT_SCRIPT = """
if (localStorage.getItem("__sculptor_mock_enabled") === "true") {
    window.sculptor = {
        // Callback registered by useAutoUpdateListener
        _autoUpdateCallback: null,

        // Initial status returned by getAutoUpdateStatus (pull on mount).
        // Default to disabled; tests override via setInitialStatus().
        _initialStatus: { type: "disabled" },

        // Set true once the consumer of getAutoUpdateStatus() has had a
        // chance to run its .then(handleStatus) and any React re-render
        // it triggered. install() polls this so tests don't race the
        // initial state hydration. See the helper below for ordering.
        _initialStatusHydrated: false,

        // Recorded IPC calls for assertion
        _ipcCalls: [],

        // --- Auto-update status (pull initial + push updates) ---
        async getAutoUpdateStatus() {
            // setTimeout(0) fires as a macrotask, after all microtasks
            // (including the consumer's .then(handleStatus) and React's
            // commit-phase scheduler) drain. By then, setStatus has run
            // and the popover content reflects the post-hydration state.
            setTimeout(() => { this._initialStatusHydrated = true; }, 0);
            return this._initialStatus;
        },
        onAutoUpdateStatus(callback) {
            this._autoUpdateCallback = callback;
            return callback;
        },
        removeAutoUpdateStatusListener(callback) {
            if (this._autoUpdateCallback === callback) {
                this._autoUpdateCallback = null;
            }
        },

        // --- Auto-update commands (renderer → main) ---
        async installUpdate() {
            this._ipcCalls.push({ method: "installUpdate", args: [] });
        },
        async checkForUpdate() {
            this._ipcCalls.push({ method: "checkForUpdate", args: [] });
        },
        async setUpdateChannel(channel) {
            this._ipcCalls.push({ method: "setUpdateChannel", args: [channel] });
        },

        // --- Stubs that must not be called during auto-update tests ---
        // Each throws so that unintended calls fail loudly.
        _notMocked(name) { throw new Error("auto_update_mock: " + name + " should not be called — the mock is only for auto-update tests"); },
        platform: "darwin",
        async selectProjectDirectory() { this._notMocked("selectProjectDirectory"); },
        async getSessionToken() { this._notMocked("getSessionToken"); },
        async getBackendPort() { this._notMocked("getBackendPort"); },
        async saveFile() { this._notMocked("saveFile"); },
        async getFileData() { this._notMocked("getFileData"); },

        // --- Backend status (pull initial + push updates) ---
        // BackendStatusBoundary pulls the initial status on mount and
        // registers a listener for subsequent push updates. The default
        // initial status is the invalid-but-harmless { status: "ready" }
        // (no matching branch in BackendStatusBoundary, so it falls
        // through to rendering children — preserving prior behaviour
        // for tests that don't care about backend status). Tests that
        // need to drive BackendStatusBoundary should call
        // ``push_backend_status`` after install.
        _initialBackendStatus: { status: "ready" },
        _backendStatusCallback: null,
        async getCurrentBackendStatus() { return this._initialBackendStatus; },
        onBackendStatusChange(callback) { this._backendStatusCallback = callback; },
        removeBackendStatusListener() { this._backendStatusCallback = null; },
        // DevModeIndicator (rendered in PageLayout footer) calls this on
        // mount; null = not running in source mode, so the indicator hides.
        async getDevInfo() { return null; },
        // useAppZoom runs unconditionally on mount and would otherwise
        // throw on these undefined methods, taking down the React tree
        // before useAutoUpdateListener can register.
        onZoomCommand(callback) { return callback; },
        removeZoomCommandListener() {},
        setZoomFactor() {},
    };
}
"""

# Track which Page objects already have the init script to avoid accumulation.
# Playwright's ``add_init_script`` has no removal API, so we register it once
# and gate activation on localStorage.
_pages_with_init_script: set[int] = set()

# How long ``install()`` waits for the mock to register its callback and for the
# initial status pull to flow through React's commit phase.
_READY_PREDICATE_TIMEOUT_MS = 10_000


class MockSculptorElectronAPI:
    """Controls a mock ``window.sculptor`` injected into a Playwright page.

    The init script is registered once per page and gated on a localStorage
    flag.  ``install()`` sets the flag and reloads; ``uninstall()`` clears the
    flag, deletes the global, and reloads so subsequent tests get a clean page.

    Use via the ``mock_electron_api`` pytest fixture which handles setup and
    teardown automatically.

    Usage::

        mock_electron_api.push_status({"type": "idle", "channel": "STABLE"})
        assert mock_electron_api.get_ipc_calls() == []
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    def install(self) -> None:
        """Inject the mock and reload the SPA so hooks pick it up on mount."""
        page_id = id(self._page)
        if page_id not in _pages_with_init_script:
            self._page.add_init_script(_MOCK_INIT_SCRIPT)
            _pages_with_init_script.add(page_id)

        # Set the gate flag, then reload so the init script creates the mock
        # before React mounts and useAutoUpdateListener runs.
        self._page.evaluate("localStorage.setItem('__sculptor_mock_enabled', 'true')")
        full_spa_reload(self._page)

        # Wait for useAutoUpdateListener to register its callback AND for
        # the initial ``getAutoUpdateStatus()`` pull to flow through
        # ``handleStatus`` and React's commit phase. The callback is set
        # synchronously inside the useEffect body, but the pull resolves
        # in a later microtask — without waiting for both, tests that
        # rely on the mock's default initial state (test_null_initial_*
        # and any test that doesn't push its own status before asserting)
        # race the still-pending pull. ``_initialStatusHydrated`` is set
        # by a ``setTimeout(0)`` from inside ``getAutoUpdateStatus``,
        # which orders after both ``handleStatus`` (microtask) and React's
        # commit (microtask) — see the mock script.
        ready_predicate = (
            "window.sculptor"
            + " && typeof window.sculptor._autoUpdateCallback === 'function'"
            + " && window.sculptor._initialStatusHydrated === true"
        )
        self._page.wait_for_function(ready_predicate, timeout=_READY_PREDICATE_TIMEOUT_MS)

    def uninstall(self) -> None:
        """Remove the mock and reload so subsequent tests get a clean page.

        Clears the localStorage gate flag and deletes ``window.sculptor``,
        then reloads.  The init script still runs on reload but sees the flag
        is absent and skips mock creation.
        """
        self._page.evaluate("localStorage.removeItem('__sculptor_mock_enabled'); delete window.sculptor")
        full_spa_reload(self._page)

    def push_status(self, status: Mapping[str, object]) -> None:
        """Invoke the callback registered by ``useAutoUpdateListener``."""
        self._page.evaluate(
            "status => window.sculptor._autoUpdateCallback(status)",
            status,
        )

    def push_backend_status(self, status: Mapping[str, object]) -> None:
        """Invoke the callback registered by ``BackendStatusBoundary``.

        Drives the React boundary as if the Electron main process pushed a
        new ``BACKEND_STATUS_CHANGE`` event. Used by tests that need to
        exercise rendering branches keyed off the backend status (e.g.
        ``shutting_down``).
        """
        self._page.evaluate(
            "status => window.sculptor._backendStatusCallback && window.sculptor._backendStatusCallback(status)",
            status,
        )

    def get_ipc_calls(self, *, method: str | None = None) -> list[dict[str, object]]:
        """Return recorded IPC calls, optionally filtered by method name."""
        calls: list[dict[str, object]] = self._page.evaluate("window.sculptor._ipcCalls")
        if method is not None:
            calls = [c for c in calls if c["method"] == method]
        return calls

    def configure_ipc_failure(self, method: str, error_message: str) -> None:
        """Make a specific IPC method reject with an error.

        Useful for testing error handling in ``handleUpdateChannelChange``
        and similar handlers.
        """
        self._page.evaluate(
            """([method, errorMessage]) => {
                window.sculptor[method] = async function(...args) {
                    window.sculptor._ipcCalls.push({ method, args });
                    throw new Error(errorMessage);
                };
            }""",
            [method, error_message],
        )


@pytest.fixture()
def mock_electron_api(
    sculptor_instance_: SculptorInstance,
    sculptor_launch_mode: str,
) -> Generator[MockSculptorElectronAPI]:
    """Install a mock ``window.sculptor`` for the duration of a single test.

    Skipped in ``packaged-electron`` mode because the real Electron preload
    script overwrites the mock via ``contextBridge.exposeInMainWorld``.
    """
    if sculptor_launch_mode == "packaged-electron":
        pytest.skip("MockSculptorElectronAPI cannot override the real Electron preload")
    mock = MockSculptorElectronAPI(sculptor_instance_.page)
    mock.install()
    yield mock
    mock.uninstall()
