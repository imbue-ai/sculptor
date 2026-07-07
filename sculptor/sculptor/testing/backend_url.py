"""Resolve the backend's HTTP origin for test-side ``page.request`` calls.

Integration-test helpers issue REST calls against the backend through
Playwright's ``page.request``. That origin must be an ``http(s)`` URL, but it
cannot be taken from ``page.url``: in packaged Electron builds the renderer is
served over the ``sculptor://app`` custom scheme, which ``page.request`` refuses
to fetch (``APIRequestContext`` only speaks ``http:``/``https:``) and which
serves no ``/api`` — the backend runs on a separate http origin. This module
centralizes obtaining that origin so every helper works in browser, Electron-dev
and packaged modes without threading the URL through their call chains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Page

if TYPE_CHECKING:
    from sculptor.testing.sculptor_instance import SculptorInstance

# Follows frontend/src/apiClient.ts ``configureClient()``'s resolution ORDER —
# prefer the Electron preload bridge's explicit backend URL (a remote/OpenHost
# backend), then its local port, else the page origin — with one deliberate
# difference: the local-port branch builds ``http://127.0.0.1:<port>``, NOT the
# ``http://localhost:<port>`` apiClient uses. This is for ``page.request``'s auth,
# not the app's. When the backend enforces a session token (packaged builds), the
# app authenticates by adding an ``x-session-token`` HEADER in ``makeAPIRequest``,
# so its host spelling is irrelevant — but ``page.request`` does NOT run that
# custom fetch; it authenticates only via the session-token COOKIE, which the
# harness scopes to ``127.0.0.1`` (see packaged_electron_frontend.py /
# resources.py). Cookies are host-specific, so a ``localhost`` URL would send no
# cookie and 403. ``127.0.0.1`` matches the cookie and equals
# ``SculptorInstance.backend_api_url`` (``server.url``), keeping the two paths
# consistent.
#
# Each strategy BOTH feature-detects the method (``typeof … === 'function'``)
# AND runs under try/catch: auto_update_mock.py injects a stub ``window.sculptor``
# whose ``getBackendPort()`` throws and which has no ``getBackendUrl`` at all, so
# a bare ``window.sculptor ? bridge : origin`` guard would take the bridge branch
# and blow up browser-mode tests running with that mock. Falling through on any
# throw keeps them on the page origin (itself ``127.0.0.1`` in browser mode).
_RESOLVE_BACKEND_URL_JS = """
async () => {
  const bridge = window.sculptor;
  try {
    if (bridge && typeof bridge.getBackendUrl === 'function') {
      const url = await bridge.getBackendUrl();
      if (url) return url;
    }
  } catch (e) { /* fall through to the port, then the page origin */ }
  try {
    if (bridge && typeof bridge.getBackendPort === 'function') {
      const port = await bridge.getBackendPort();
      if (port) return `http://127.0.0.1:${port}`;
    }
  } catch (e) { /* fall through to the page origin */ }
  return window.location.origin;
}
"""


def resolve_backend_api_url(page_or_instance: Page | SculptorInstance) -> str:
    """Return the backend's HTTP origin (no trailing slash) for ``page.request``.

    Given a ``SculptorInstance``, returns its ``backend_api_url`` directly — the
    exact origin the harness started the backend on. Given only a ``Page``,
    evaluates the renderer's own resolution (see ``_RESOLVE_BACKEND_URL_JS``).
    Both paths yield the same ``http://127.0.0.1:<port>`` origin, which matters:
    ``page.request`` authenticates via the session-token COOKIE, and the harness
    scopes that cookie to ``127.0.0.1`` — a ``localhost`` spelling would send no
    cookie and 403 against a token-protected backend. The Page path is only valid
    once the app page has loaded and the preload bridge has initialized; every
    current caller runs mid-test, after navigation, so that holds.
    """
    # Duck-type rather than isinstance() so unit tests can pass a lightweight
    # fake page (which has ``evaluate`` but no ``backend_api_url``). A real
    # Playwright ``Page`` has no ``backend_api_url`` attribute, so it takes the
    # evaluate path.
    backend_api_url = getattr(page_or_instance, "backend_api_url", None)
    if backend_api_url is not None:
        return backend_api_url.rstrip("/")

    resolved = page_or_instance.evaluate(_RESOLVE_BACKEND_URL_JS)
    # Fail loudly if the renderer ever stops exposing an http origin (e.g. the
    # preload bridge is renamed and the fallback lands on ``sculptor://app``):
    # keep this in sync with frontend/src/apiClient.ts configureClient(). A
    # silent ``sculptor://`` here would resurface as the opaque
    # "Protocol \"sculptor:\" not supported" page.request error.
    assert isinstance(resolved, str) and resolved.startswith("http"), (
        f"resolve_backend_api_url got a non-http backend origin {resolved!r}; the Electron "
        + "preload bridge (window.sculptor) may have been renamed — keep this resolver in "
        + "sync with frontend/src/apiClient.ts configureClient()."
    )
    return resolved.rstrip("/")
