"""Page Object Model for the Browser panel.

Wraps the panel root locator and exposes typed accessors for the URL
input, navigation buttons, and webview-bridge calls used by Browser
panel integration tests.
"""

from __future__ import annotations

import re
import time
from typing import Any

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# The Browser panel surfaces the active workspace's committed webview status on
# the panel root via data-webview-content-id (the attached guest's
# webContentsId, present once did-attach fires) and data-webview-current-url
# (the committed URL, updated on did-navigate). These are the production-truth
# readiness signals the page object gates on, keyed to the active workspace
# rather than a focus-coupled global or a guest round-trip.
_WEBVIEW_CONTENT_ID_ATTR: str = "data-webview-content-id"
_WEBVIEW_CURRENT_URL_ATTR: str = "data-webview-current-url"

# The guest can take well over 10s to attach under heavy CI parallelism (xvfb +
# software rendering), so give the attach wait a generous budget.
_WEBVIEW_ATTACH_TIMEOUT_SECONDS: float = 30.0
_URL_POLL_INTERVAL_SECONDS: float = 0.1
_DEFAULT_ADDRESS_BAR_TIMEOUT_SECONDS: float = 10.0
_PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"
# The screenshot -> clipboard round-trip goes through Electron's main process
# and the OS clipboard, which under xvfb can take longer than a local run. Match
# the attach budget so a slow-but-healthy CI host isn't mistaken for a missing
# screenshot.
_CLIPBOARD_TIMEOUT_SECONDS: float = 30.0

# How long ``webview_evaluate`` retries a transient execute error before giving
# up. The injected script can throw for a beat -- e.g. ``getElementById(...)`` is
# null right after a re-focus -- which Electron surfaces as "Script failed to
# execute"; retrying rides through that window. A genuine error still surfaces
# once the budget is exhausted.
_WEBVIEW_EXECUTE_RETRY_SECONDS: float = 15.0

# Budget for navigate() to land a typed URL and have the webview commit it. A
# workspace switch can remount the panel mid-fill, so we re-issue fill+Enter on a
# freshly-resolved input until the committed URL moves; each attempt's wait is
# short so the budget supplies the overall wait.
_NAVIGATE_RETRY_SECONDS: float = 30.0
_NAVIGATE_ATTEMPT_SECONDS: float = 3.0

# Substrings that mark a webview-execute failure as a transient "guest not ready
# yet" condition rather than a real assertion failure. Matched against the
# Playwright error text bubbled up from the Electron ``executeJavaScript`` IPC.
_TRANSIENT_WEBVIEW_EXECUTE_MARKERS: tuple[str, ...] = (
    # Electron's executeJavaScript rejects with this when the guest's page threw
    # (e.g. a null element during a load) or the target webContents is gone.
    "Script failed to execute",
    # The bridge is briefly absent while window.sculptor is still initializing.
    "browser panel test bridge not available",
)


class PlaywrightBrowserPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Browser panel."""

    def get_root(self) -> Locator:
        """Return the panel root (``BROWSER_PANEL``) locator this POM wraps.

        Lets tests assert the panel's open/closed state through the POM
        instead of re-deriving ``ElementIDs.BROWSER_PANEL`` inline.
        """
        return self._locator

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

        By default we wait for the webview to *commit* the navigation, read from
        the panel's ``data-webview-current-url`` attribute (the committed URL
        published on the guest's ``did-navigate``). That is the production-truth
        signal that the guest actually loaded ``url``: a per-workspace DOM read,
        so it needs no focus-coupled global and no guest ``document.location``
        round-trip.

        Set ``wait_for_webview_load=False`` for negative-path tests where the
        URL is intentionally invalid and the webview will never commit it; those
        only confirm the address bar took the typed text.

        The fill is re-issued on a freshly-resolved URL input each attempt: a
        workspace switch can remount the panel so a one-shot fill lands in the
        old, detaching input and the committed URL never moves. Re-issuing
        fill+Enter on the live input until the committed URL reaches ``url``
        lands the value.
        """
        bare_url = url.split("#", 1)[0]
        deadline = time.monotonic() + _NAVIGATE_RETRY_SECONDS
        while True:
            input_locator = self.get_url_input()
            expect(input_locator).to_be_visible()
            input_locator.click(click_count=3)
            input_locator.fill(url)
            input_locator.press("Enter")
            if not wait_for_webview_load:
                self.wait_for_address_bar_contains(bare_url, timeout_seconds=_NAVIGATE_ATTEMPT_SECONDS)
                return
            if self._committed_url_contains(bare_url, timeout_seconds=_NAVIGATE_ATTEMPT_SECONDS):
                return
            if time.monotonic() >= deadline:
                last = self._committed_url()
                raise AssertionError(
                    f"Webview did not commit navigation to {bare_url!r}; last committed URL was {last!r}"
                )

    def click_back(self) -> None:
        self.get_back_button().click()

    def click_forward(self) -> None:
        self.get_forward_button().click()

    def click_refresh(self) -> None:
        self.get_refresh_button().click()

    def click_screenshot(self) -> None:
        self.get_screenshot_button().click()

    def webview_evaluate(self, code: str) -> Any:
        """Run ``code`` inside the active panel's webview guest via the test-only IPC.

        The guest is targeted by the webContentsId read from the panel's
        ``data-webview-content-id`` attribute (re-read each attempt so a guest
        re-created by a workspace switch is picked up rather than executed into
        while it is still attaching). Transient execute failures (see
        ``_TRANSIENT_WEBVIEW_EXECUTE_MARKERS``) are retried for up to
        ``_WEBVIEW_EXECUTE_RETRY_SECONDS``; a non-transient error is re-raised
        immediately, a transient one once the budget is spent.
        """
        deadline = time.monotonic() + _WEBVIEW_EXECUTE_RETRY_SECONDS
        while True:
            content_id = self._attached_content_id()
            try:
                return self._page.evaluate(
                    """async ([id, code]) => {
                      const api = window.sculptor;
                      if (!api || !api.__testBrowserWebviewExecute) {
                        throw new Error('browser panel test bridge not available');
                      }
                      return api.__testBrowserWebviewExecute(id, code);
                    }""",
                    [content_id, code],
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

    def _committed_url(self) -> str:
        """The webview's committed URL, from the panel's data-webview-current-url."""
        return self.get_attribute(_WEBVIEW_CURRENT_URL_ATTR) or ""

    def _committed_url_contains(self, needle: str, *, timeout_seconds: float) -> bool:
        """Whether the committed URL reaches ``needle`` within ``timeout_seconds``."""
        try:
            expect(self._locator).to_have_attribute(
                _WEBVIEW_CURRENT_URL_ATTR,
                re.compile(re.escape(needle)),
                timeout=int(timeout_seconds * 1000),
            )
            return True
        except AssertionError:
            return False

    def _attached_content_id(self) -> int:
        """Return the attached guest's webContentsId, waiting until it attaches.

        Reads the panel's ``data-webview-content-id`` attribute, which is absent
        until the active workspace's guest fires ``did-attach`` and then holds
        its webContentsId. Times out via Playwright's ``to_have_attribute`` if
        the guest never attaches.
        """
        expect(self._locator).to_have_attribute(
            _WEBVIEW_CONTENT_ID_ATTR,
            re.compile(r"\d+"),
            timeout=int(_WEBVIEW_ATTACH_TIMEOUT_SECONDS * 1000),
        )
        value = self.get_attribute(_WEBVIEW_CONTENT_ID_ATTR)
        assert value is not None  # to_have_attribute above guarantees presence
        return int(value)
