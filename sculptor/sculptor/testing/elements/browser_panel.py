"""Page Object Model for the Browser panel.

Wraps the panel root locator and exposes typed accessors for the URL
input, navigation buttons, and webview-bridge calls used by Browser
panel integration tests.
"""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# Waits that depend on the <webview> guest attaching and committing a
# navigation (vs. the address bar, which mirrors the typed URL instantly). The
# guest can take well over 10s to attach and load under heavy CI parallelism
# (xvfb + software rendering), so give these a generous budget.
_WEBVIEW_ATTACH_TIMEOUT_SECONDS: float = 30.0
_WEBVIEW_LOAD_TIMEOUT_SECONDS: float = 30.0
_URL_POLL_INTERVAL_SECONDS: float = 0.1
_DEFAULT_ADDRESS_BAR_TIMEOUT_SECONDS: float = 10.0
_PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"
# The screenshot -> clipboard round-trip goes through Electron's main process
# and the OS clipboard, which under xvfb + software rendering can take well
# over the snappy budget a local run sees. Match the webview load budget so a
# slow-but-healthy CI host isn't mistaken for a missing screenshot.
_CLIPBOARD_TIMEOUT_SECONDS: float = 30.0

# How long ``webview_evaluate`` retries a *transient* bridge error before giving
# up. A workspace switch or panel reopen re-creates the guest webContents, and
# for a short window the test bridge can point at a guest that is mid-load or
# just re-attached. Executing into it then rejects; retrying (and re-reading the
# current webContentsId each attempt) lets the guest settle. The injected script
# itself can also throw transiently -- e.g. ``getElementById(...)`` is null for a
# beat right after re-focus -- which Electron surfaces as "Script failed to
# execute". A genuine error still surfaces once the budget is exhausted.
_WEBVIEW_EXECUTE_RETRY_SECONDS: float = 15.0

# Budget for navigate() to land a typed URL, across re-resolutions of the URL
# input. A workspace switch remounts the panel, so a one-shot fill can land in
# the old, detaching input while the new one still shows the persisted
# about:blank. We re-issue fill+Enter on a freshly-resolved input within this
# window; each attempt's address-bar check is short so the budget supplies the
# overall wait (the retry pattern, not a lowered single timeout).
_NAVIGATE_RETRY_SECONDS: float = 30.0
_NAVIGATE_ATTEMPT_SECONDS: float = 3.0

# Substrings that mark a webview-execute failure as a transient "guest not ready
# yet" condition rather than a real assertion failure. Matched against the
# Playwright error text bubbled up from the Electron ``executeJavaScript`` IPC.
_TRANSIENT_WEBVIEW_EXECUTE_MARKERS: tuple[str, ...] = (
    # Electron's executeJavaScript rejects with this when the guest's page threw
    # (e.g. a null element during a load) or the target webContents is gone.
    "Script failed to execute",
    # The bridge is briefly absent while focus moves between workspace slots.
    "browser panel test bridge not available",
    # loadURL/eval before the <webview> has fired did-attach.
    "WebView must be attached",
)


class PlaywrightBrowserPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Browser panel."""

    def get_web_mode_placeholder(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BROWSER_WEB_MODE_PLACEHOLDER)

    def get_url_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BROWSER_URL_INPUT)

    def get_url_error(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BROWSER_URL_ERROR)

    def get_back_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BROWSER_BACK_BTN)

    def get_forward_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BROWSER_FORWARD_BTN)

    def get_refresh_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BROWSER_REFRESH_BTN)

    def get_screenshot_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BROWSER_SCREENSHOT_BTN)

    def get_address_bar_value(self) -> str:
        return self.get_url_input().input_value()

    def navigate(self, url: str, *, wait_for_webview_load: bool = True) -> None:
        """Type ``url`` into the address bar, press Enter, and wait for navigation.

        The address bar mirrors whatever the user typed the moment Enter is
        pressed, but the webview's ``did-navigate`` event (which feeds the
        per-workspace persisted-URL atom) is async. By default we additionally
        wait for the webview's live ``document.location`` to reach ``url``,
        so callers that immediately collapse the panel see the persisted URL
        on reopen instead of a stale ``about:blank``.

        Set ``wait_for_webview_load=False`` for negative-path tests where the
        URL is intentionally invalid and the webview will never reach it.

        The fill is retried on a freshly-resolved URL input each attempt: a
        workspace switch remounts the panel, so a one-shot fill can land in the
        old, detaching input while the address bar then reads the new input
        (still showing the persisted ``about:blank``). Re-issuing fill+Enter on
        the live input lands the value.
        """
        bare_url = url.split("#", 1)[0]
        deadline = time.monotonic() + _NAVIGATE_RETRY_SECONDS
        while True:
            input_locator = self.get_url_input()
            expect(input_locator).to_be_visible()
            input_locator.click(click_count=3)
            input_locator.fill(url)
            input_locator.press("Enter")
            try:
                self.wait_for_address_bar_contains(bare_url, timeout_seconds=_NAVIGATE_ATTEMPT_SECONDS)
                break
            except AssertionError:
                if time.monotonic() >= deadline:
                    raise
        if wait_for_webview_load:
            self._wait_for_webview_location_contains(bare_url)

    def click_back(self) -> None:
        self.get_back_button().click()

    def click_forward(self) -> None:
        self.get_forward_button().click()

    def click_refresh(self) -> None:
        self.get_refresh_button().click()

    def click_screenshot(self) -> None:
        self.get_screenshot_button().click()

    def webview_evaluate(self, code: str) -> Any:
        """Run ``code`` inside the panel's webview guest page via the test-only IPC.

        Retries transient "guest not ready" failures (see
        ``_TRANSIENT_WEBVIEW_EXECUTE_MARKERS``) for up to
        ``_WEBVIEW_EXECUTE_RETRY_SECONDS``, re-reading the current
        ``webContentsId`` each attempt so a guest re-created by a workspace
        switch or panel reopen is picked up rather than executed into while it
        is still attaching. A non-transient error (a real bug, or the bridge
        being absent because the test runs in browser-launch mode) is re-raised
        immediately; a transient one is re-raised only once the budget is spent.
        """
        deadline = time.monotonic() + _WEBVIEW_EXECUTE_RETRY_SECONDS
        while True:
            # Re-resolve the bridge each attempt: the webContentsId mirrored onto
            # window.__BROWSER_PANEL_TEST__ changes when the focused workspace's
            # guest is re-created, so a value cached across the retry loop could
            # point at a torn-down webContents.
            self._wait_for_webview_attached()
            try:
                return self._page.evaluate(
                    """async (code) => {
                      const api = window.sculptor;
                      const test = window.__BROWSER_PANEL_TEST__;
                      if (!api || !api.__testBrowserWebviewExecute || !test) {
                        throw new Error('browser panel test bridge not available');
                      }
                      return api.__testBrowserWebviewExecute(test.webContentsId, code);
                    }""",
                    code,
                )
            except Exception as exc:  # noqa: BLE001 — re-raised below unless transient
                message = str(exc)
                is_transient = any(marker in message for marker in _TRANSIENT_WEBVIEW_EXECUTE_MARKERS)
                if not is_transient or time.monotonic() >= deadline:
                    raise
                self._page.wait_for_timeout(int(_URL_POLL_INTERVAL_SECONDS * 1000))

    def read_clipboard_png_bytes(self) -> bytes | None:
        """Read the PNG bytes currently on the system clipboard.

        Returns ``None`` if the clipboard has no image. Raises
        ``RuntimeError`` if the Electron test bridge is not installed.
        """
        result = self._page.evaluate(
            """async () => {
              const api = window.sculptor;
              if (!api || !api.__testReadClipboardPng) {
                throw new Error('clipboard PNG test bridge not available');
              }
              const buffer = await api.__testReadClipboardPng();
              if (buffer === null) return null;
              return Array.from(new Uint8Array(buffer));
            }"""
        )
        if result is None:
            return None
        return bytes(result)

    def wait_for_clipboard_png(self, *, timeout_seconds: float = _CLIPBOARD_TIMEOUT_SECONDS) -> bytes:
        """Poll the clipboard until a PNG appears, or fail."""
        deadline = time.monotonic() + timeout_seconds
        last: bytes | None = None
        while time.monotonic() < deadline:
            last = self.read_clipboard_png_bytes()
            if last is not None and last.startswith(_PNG_MAGIC):
                return last
            self._page.wait_for_timeout(int(_URL_POLL_INTERVAL_SECONDS * 1000))
        raise AssertionError(f"No PNG on clipboard after {timeout_seconds}s (last={last!r})")

    def wait_for_address_bar_contains(
        self, needle: str, *, timeout_seconds: float = _DEFAULT_ADDRESS_BAR_TIMEOUT_SECONDS
    ) -> None:
        """Wait until the address bar reflects a URL containing ``needle``."""
        deadline = time.monotonic() + timeout_seconds
        last_value = ""
        while time.monotonic() < deadline:
            last_value = self.get_address_bar_value()
            if needle in last_value:
                return
            self._page.wait_for_timeout(int(_URL_POLL_INTERVAL_SECONDS * 1000))
        raise AssertionError(f"Address bar did not contain {needle!r}; last value was {last_value!r}")

    def _wait_for_webview_location_contains(
        self, needle: str, *, timeout_seconds: float = _WEBVIEW_LOAD_TIMEOUT_SECONDS
    ) -> None:
        """Wait until the webview's live ``document.location`` reflects ``needle``.

        Used to gate on the webview's ``did-navigate`` event having fired —
        the address bar in the toolbar reflects the *typed* URL, but the
        per-workspace persisted-URL atom is only updated when the webview
        actually emits ``did-navigate``.
        """
        deadline = time.monotonic() + timeout_seconds
        last_value = ""
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                last_value = str(self.webview_evaluate("document.location.href"))
                last_error = None
            except Exception as exc:  # noqa: BLE001 — bridge may briefly raise mid-navigation
                last_value = ""
                last_error = exc
            if needle in last_value:
                return
            self._page.wait_for_timeout(int(_URL_POLL_INTERVAL_SECONDS * 1000))
        # Surface the last bridge error if we never got a readable location: a
        # bare "last value was ''" hides a persistently-stale webContentsId,
        # which is the failure mode worth diagnosing when this does trip.
        suffix = f" (last webview-execute error: {last_error})" if last_error is not None else ""
        raise AssertionError(f"Webview location did not reach {needle!r}; last value was {last_value!r}{suffix}")

    def _wait_for_webview_attached(self) -> None:
        deadline = time.monotonic() + _WEBVIEW_ATTACH_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            is_ready = self._page.evaluate(
                "() => Boolean(window.__BROWSER_PANEL_TEST__ && window.__BROWSER_PANEL_TEST__.webContentsId)"
            )
            if is_ready:
                return
            time.sleep(_URL_POLL_INTERVAL_SECONDS)
        raise TimeoutError("Timed out waiting for webview did-attach")
