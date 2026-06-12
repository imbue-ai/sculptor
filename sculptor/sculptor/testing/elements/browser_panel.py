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

_WEBVIEW_ATTACH_TIMEOUT_SECONDS: float = 10.0
_URL_POLL_INTERVAL_SECONDS: float = 0.1
_DEFAULT_ADDRESS_BAR_TIMEOUT_SECONDS: float = 10.0
_PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"
_CLIPBOARD_TIMEOUT_SECONDS: float = 10.0


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
        """
        input_locator = self.get_url_input()
        expect(input_locator).to_be_visible()
        input_locator.click(click_count=3)
        input_locator.fill(url)
        input_locator.press("Enter")
        bare_url = url.split("#", 1)[0]
        self.wait_for_address_bar_contains(bare_url)
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

        Raises ``RuntimeError`` if the Electron bridge is not installed (e.g. when
        the test is running in browser-launch mode rather than Electron).
        """
        self._wait_for_webview_attached()
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
        self, needle: str, *, timeout_seconds: float = _DEFAULT_ADDRESS_BAR_TIMEOUT_SECONDS
    ) -> None:
        """Wait until the webview's live ``document.location`` reflects ``needle``.

        Used to gate on the webview's ``did-navigate`` event having fired —
        the address bar in the toolbar reflects the *typed* URL, but the
        per-workspace persisted-URL atom is only updated when the webview
        actually emits ``did-navigate``.
        """
        deadline = time.monotonic() + timeout_seconds
        last_value = ""
        while time.monotonic() < deadline:
            try:
                last_value = str(self.webview_evaluate("document.location.href"))
            except Exception:  # noqa: BLE001 — bridge may briefly raise mid-navigation
                last_value = ""
            if needle in last_value:
                return
            self._page.wait_for_timeout(int(_URL_POLL_INTERVAL_SECONDS * 1000))
        raise AssertionError(f"Webview location did not reach {needle!r}; last value was {last_value!r}")

    def _wait_for_webview_attached(self) -> None:
        deadline = time.monotonic() + _WEBVIEW_ATTACH_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            ready = self._page.evaluate(
                "() => Boolean(window.__BROWSER_PANEL_TEST__ && window.__BROWSER_PANEL_TEST__.webContentsId)"
            )
            if ready:
                return
            time.sleep(_URL_POLL_INTERVAL_SECONDS)
        raise TimeoutError("Timed out waiting for webview did-attach")
