"""Local HTTP server that serves extension manifests and bundles for loader tests.

The frontend loads an extension by fetching ``<source>/manifest.json`` and then
dynamic-importing the entry module named in it. This fixture server stands up
those two responses on a real cross-origin origin (``http://127.0.0.1:<port>``,
the way an extension dev server would look) with per-route control over the body,
content type, and whether CORS headers are sent -- enough to drive a successful
load as well as every failure mode: malformed manifest JSON, a manifest that
fails validation, a blocked-by-CORS fetch, a missing entry module, and a module
that has no default export or throws while activating.

Modeled on ``browser_panel_fixture_server.py`` (safe random port, daemon
thread, explicit shutdown), but routes are held in memory rather than served
from a directory so a test can declare each fixture inline.
"""

from __future__ import annotations

import dataclasses
import http.server
import json
import random
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

# Bind inside the IANA dynamic/private range, above Chromium's unsafe-ports
# list and inside the OS ephemeral pools -- same rationale as the browser-panel
# fixture server.
_SAFE_PORT_MIN: int = 49152
_SAFE_PORT_MAX: int = 60999
_MAX_PORT_RETRIES: int = 8


@dataclasses.dataclass(frozen=True)
class _Route:
    status: int
    content_type: str
    body: bytes
    cors: bool


class _ExtensionFixtureHTTPServer(http.server.ThreadingHTTPServer):
    """A threaded HTTP server carrying the route table its handler serves."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[http.server.BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.routes: dict[str, _Route] = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def _routes(self) -> dict[str, _Route]:
        return cast("_ExtensionFixtureHTTPServer", self.server).routes

    def _lookup(self) -> _Route | None:
        # Ignore any query string: reloads append a `?t=<cache-bust>` token.
        path = self.path.split("?", 1)[0]
        return self._routes().get(path)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler dispatch name)
        route = self._lookup()
        if route is None:
            # Reachable but missing: a CORS-allowed 404, so the loader sees an
            # `HTTP 404` (its manifest-phase error) rather than a CORS failure.
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(route.status)
        self.send_header("Content-Type", route.content_type)
        self.send_header("Content-Length", str(len(route.body)))
        if route.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(route.body)

    def do_OPTIONS(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler dispatch name)
        # Simple GETs don't preflight, but answer permissively so a stray
        # preflight never masks the behavior under test.
        route = self._lookup()
        self.send_response(204)
        if route is None or route.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        # Keep the test output quiet; the default logs every request to stderr.
        pass


@dataclasses.dataclass(frozen=True)
class ExtensionFixtureServer:
    base_url: str
    port: int
    _server: _ExtensionFixtureHTTPServer
    _thread: threading.Thread

    def add_route(
        self,
        path: str,
        *,
        body: str | bytes,
        content_type: str,
        status: int = 200,
        cors: bool = True,
    ) -> None:
        """Register a raw response for an exact request path (e.g. ``/x/manifest.json``)."""
        data = body.encode("utf-8") if isinstance(body, str) else body
        self._server.routes[path] = _Route(status=status, content_type=content_type, body=data, cors=cors)

    def add_extension(
        self,
        extension_id: str,
        *,
        manifest: str | dict[str, object],
        entry_js: str | None = None,
        entry_name: str = "main.js",
        cors: bool = True,
    ) -> str:
        """Register an extension's manifest (and optional entry module); return its source URL.

        ``manifest`` is serialized to JSON when given as a dict, or sent verbatim
        as a string (to inject malformed JSON). ``entry_js`` is the entry module
        body; omit it to leave the entry path returning 404 (an import-phase
        failure). ``cors=False`` drops the CORS header so the cross-origin fetch
        is blocked (a manifest-phase failure). Returns the source a test hands to
        ``add_source`` -- the extension directory URL, without ``/manifest.json``.
        """
        manifest_body = manifest if isinstance(manifest, str) else json.dumps(manifest)
        self.add_route(
            f"/{extension_id}/manifest.json", body=manifest_body, content_type="application/json", cors=cors
        )
        if entry_js is not None:
            self.add_route(f"/{extension_id}/{entry_name}", body=entry_js, content_type="text/javascript", cors=cors)
        return self.source_for(extension_id)

    def source_for(self, extension_id: str) -> str:
        return f"{self.base_url}/{extension_id}"

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _start_server() -> ExtensionFixtureServer:
    for _attempt in range(_MAX_PORT_RETRIES):
        port = random.randint(_SAFE_PORT_MIN, _SAFE_PORT_MAX)
        try:
            server = _ExtensionFixtureHTTPServer(("127.0.0.1", port), _Handler)
        except OSError:
            continue
        thread = threading.Thread(target=server.serve_forever, name="extension-fixture", daemon=True)
        thread.start()
        return ExtensionFixtureServer(base_url=f"http://127.0.0.1:{port}", port=port, _server=server, _thread=thread)
    raise RuntimeError(
        f"Could not bind a port in [{_SAFE_PORT_MIN}, {_SAFE_PORT_MAX}] after {_MAX_PORT_RETRIES} attempts"
    )


@contextmanager
def spawn_extension_fixture_server() -> Iterator[ExtensionFixtureServer]:
    """Start the fixture server for the duration of a test, then shut it down."""
    server = _start_server()
    try:
        yield server
    finally:
        server.shutdown()
