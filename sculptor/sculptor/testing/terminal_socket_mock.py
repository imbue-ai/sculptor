"""Capture the terminal WebSockets the app opens, so tests can drop them.

Playwright cannot close an already-established loopback WebSocket from a test
(offline emulation does not drop loopback sockets, and ``route_web_socket``
needs its shim injected at document load). To exercise the terminal's
reconnect/connection-state behaviour we instead wrap the global ``WebSocket``
constructor via ``add_init_script`` so every terminal socket the *real* app
creates is recorded on ``window.__terminalSockets``. A test can then close the
live socket with a chosen code and assert how the UI reacts.

This mirrors ``auto_update_mock.py``: the init script is gated on a
``localStorage`` flag so non-terminal tests sharing the page are unaffected,
and ``install()`` / ``uninstall()`` toggle the flag and reload.

No production code is involved — the wrapper only observes the sockets the app
already opens (and forwards construction to the real ``WebSocket`` via a
``Proxy``, preserving statics like ``WebSocket.OPEN`` and ``instanceof``).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from playwright.sync_api import Page

from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.sculptor_instance import SculptorInstance

# Runs before any page scripts. Only wraps WebSocket when the gate flag is set,
# so other tests sharing the same page instance are unaffected. The Proxy keeps
# the native constructor's behaviour (statics, instanceof) and just records the
# terminal sockets as they are created.
_CAPTURE_INIT_SCRIPT = """
if (localStorage.getItem("__sculptor_terminal_socket_capture") === "true") {
    window.__terminalSockets = [];
    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = new Proxy(OriginalWebSocket, {
        construct(target, args) {
            const socket = new target(...args);
            try {
                if (String(args[0] ?? "").includes("/terminal/")) {
                    window.__terminalSockets.push(socket);
                }
            } catch (e) {
                // Ignore — capture is best-effort and must never break the app.
            }
            return socket;
        },
    });
}
"""

# Playwright's add_init_script has no removal API, so register it once per page
# and gate activation on localStorage.
_pages_with_init_script: set[int] = set()


class TerminalSocketCapture:
    """Captures and drops the terminal WebSockets the app opens.

    Use via the ``terminal_socket_capture`` fixture, which installs the capture
    before the test runs and tears it down afterwards.
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    def install(self) -> None:
        """Wrap ``WebSocket`` and reload so the wrapper is active before the app mounts."""
        page_id = id(self._page)
        if page_id not in _pages_with_init_script:
            self._page.add_init_script(_CAPTURE_INIT_SCRIPT)
            _pages_with_init_script.add(page_id)
        self._page.evaluate("localStorage.setItem('__sculptor_terminal_socket_capture', 'true')")
        full_spa_reload(self._page)

    def uninstall(self) -> None:
        """Clear the gate flag and reload so subsequent tests get a clean page."""
        self._page.evaluate(
            "localStorage.removeItem('__sculptor_terminal_socket_capture'); delete window.__terminalSockets"
        )
        full_spa_reload(self._page)

    def wait_for_connection(self) -> None:
        """Wait until the app has opened at least one terminal WebSocket."""
        self._page.wait_for_function("(window.__terminalSockets || []).length > 0")

    def socket_count(self) -> int:
        """How many terminal WebSockets have been opened so far (incl. reconnects)."""
        return self._page.evaluate("(window.__terminalSockets || []).length")

    def wait_for_additional_connection(self, *, since: int, timeout_ms: int = 30_000) -> None:
        """Wait until more than ``since`` terminal sockets have been opened (a reconnect).

        Defaults to the harness's standard 30s; reconnect waits ~2s plus the
        backend's buffer replay, which can run longer under CI load.
        """
        self._page.wait_for_function(
            "expected => (window.__terminalSockets || []).length > expected",
            arg=since,
            timeout=timeout_ms,
        )

    def wait_for_latest_open(self, *, timeout_ms: int = 30_000) -> None:
        """Wait until the most recently opened terminal socket has reached OPEN.

        Sockets are captured at construction (before ``onopen``), and the app
        silently drops keystrokes sent before ``readyState`` is OPEN, so type
        only after this returns. ``1`` is ``WebSocket.OPEN``.
        """
        self._page.wait_for_function(
            """() => {
                const sockets = window.__terminalSockets || [];
                const ws = sockets[sockets.length - 1];
                return Boolean(ws) && ws.readyState === 1;
            }""",
            timeout=timeout_ms,
        )

    def drop_latest(self, *, code: int) -> None:
        """Close the most recently opened terminal WebSocket with ``code``.

        Closing from JS always produces a clean close frame, so ``code`` must be
        a valid application close code (1000, or 3000–4999) — enough to exercise
        every reconnect branch (retryable vs. the non-retryable 1000 / 4401).
        """
        self._page.evaluate(
            """code => {
                const sockets = window.__terminalSockets || [];
                const socket = sockets[sockets.length - 1];
                if (!socket) {
                    throw new Error("no terminal WebSocket captured to drop");
                }
                socket.close(code);
            }""",
            code,
        )


@pytest.fixture()
def terminal_socket_capture(sculptor_instance_: SculptorInstance) -> Generator[TerminalSocketCapture]:
    """Install terminal-WebSocket capture for the duration of a single test."""
    capture = TerminalSocketCapture(sculptor_instance_.page)
    capture.install()
    yield capture
    capture.uninstall()
