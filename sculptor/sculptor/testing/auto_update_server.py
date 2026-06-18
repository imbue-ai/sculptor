"""Local HTTP server for Electron auto-update integration tests.

Serves configurable ``latest-mac.yml`` / ``latest-linux.yml`` /
``latest-linux-arm64.yml`` manifests and fake artifact files so that
``electron-updater`` can complete its full update lifecycle against a local
endpoint instead of S3.

The server's state is mutable: tests call ``set_update(version, artifact)`` to
change what the next request returns, or ``set_no_update(current_version)`` to
simulate "already up to date".

Usage::

    server = AutoUpdateTestServer(port=12345)
    server.start()
    server.set_update("99.0.0", b"fake-zip-content")
    # ... electron-updater hits http://localhost:12345/slim/zip/darwin/arm64/latest-mac.yml
    server.stop()
"""

from __future__ import annotations

import base64
import hashlib
import io
import platform
import sys
import threading
import time
import zipfile
from datetime import datetime
from datetime import timezone
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from typing import Generator
from urllib.parse import urlparse

import pytest
from loguru import logger

from sculptor.testing.port_manager import PortManager

# Number of chunks the artifact is split into when ``artifact_chunk_delay`` is
# set, so ``electron-updater`` emits several ``download-progress`` events.
_ARTIFACT_CHUNK_COUNT = 10
# How long ``stop()`` waits for the server thread to exit before giving up.
_THREAD_JOIN_TIMEOUT_SECONDS = 5.0


def _manifest_filename() -> str:
    if sys.platform == "darwin":
        return "latest-mac.yml"
    return "latest-linux-arm64.yml" if platform.machine() == "aarch64" else "latest-linux.yml"


def _artifact_filename(version: str) -> str:
    if sys.platform == "darwin":
        return f"Sculptor-darwin-arm64-{version}.zip"
    return "Sculptor.AppImage"


def _make_darwin_app_zip(version: str) -> bytes:
    """Create a minimal macOS app bundle zip that Squirrel.Mac can process.

    Squirrel.Mac expects the zip to contain a ``*.app`` directory with a
    valid ``Contents/Info.plist`` including ``CFBundleVersion``.
    """
    plist = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.imbue.sculptor.test</string>
    <key>CFBundleVersion</key>
    <string>{version}</string>
    <key>CFBundleShortVersionString</key>
    <string>{version}</string>
    <key>CFBundleExecutable</key>
    <string>Sculptor</string>
</dict>
</plist>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Sculptor.app/Contents/Info.plist", plist)
        # Squirrel also needs a (possibly empty) executable
        zf.writestr("Sculptor.app/Contents/MacOS/Sculptor", "#!/bin/sh\nexit 0\n")
    return buf.getvalue()


class _ServerState:
    """Thread-safe mutable state shared between the HTTP handler and the test."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.manifest_yaml: str = ""
        self.artifact_content: bytes = b""
        self.artifact_filename: str = ""
        self.artifact_chunk_delay: float = 0.0
        self.is_offline: bool = False
        self.request_paths: list[str] = []
        self.request_user_agents: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    """Handles requests from ``electron-updater``."""

    server_state: _ServerState  # set by the factory

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        logger.debug("[auto-update-server] {} {} -> {}", self.command, self.path, code)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        user_agent = self.headers.get("User-Agent", "")
        with self.server_state.lock:
            self.server_state.request_paths.append(path)
            self.server_state.request_user_agents.append(user_agent)
            is_offline = self.server_state.is_offline
            manifest_yaml = self.server_state.manifest_yaml
            artifact_content = self.server_state.artifact_content
            artifact_filename = self.server_state.artifact_filename
            chunk_delay = self.server_state.artifact_chunk_delay

        if is_offline:
            self._respond(503, b"Service Unavailable", "text/plain")
            return

        # ``path`` was already parsed above (query params stripped).
        # Extract the basename for matching.
        basename = path.rsplit("/", 1)[-1]

        if basename == _manifest_filename():
            self._respond(200, manifest_yaml.encode(), "text/yaml")
        elif basename == artifact_filename:
            if chunk_delay > 0:
                self._respond_chunked(artifact_content, "application/octet-stream", chunk_delay)
            else:
                self._respond(200, artifact_content, "application/octet-stream")
        else:
            self._respond(404, b"Not Found", "text/plain")

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond_chunked(self, body: bytes, content_type: str, chunk_delay: float) -> None:
        """Send the response in chunks with delays to produce download-progress events."""
        chunk_size = max(1, len(body) // _ARTIFACT_CHUNK_COUNT)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        for offset in range(0, len(body), chunk_size):
            self.wfile.write(body[offset : offset + chunk_size])
            self.wfile.flush()
            time.sleep(chunk_delay)


class AutoUpdateTestServer:
    """A local HTTP server that mimics the S3 update feed for integration tests."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._state = _ServerState()
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self) -> None:
        handler_class = type("BoundHandler", (_Handler,), {"server_state": self._state})
        self._httpd = HTTPServer(("127.0.0.1", self._port), handler_class)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)

    def set_update(
        self,
        version: str,
        artifact_content: bytes | None = None,
        *,
        artifact_chunk_delay: float = 0.0,
    ) -> None:
        """Configure the server to advertise ``version`` as available.

        If ``artifact_content`` is not provided, a small placeholder is used.
        The manifest's SHA-512 and size are computed from the artifact content
        so that ``electron-updater``'s integrity check passes.

        When ``artifact_chunk_delay`` is set, the artifact is served in several
        chunks with a delay between each, forcing ``electron-updater`` to emit
        ``download-progress`` events that the UI can observe.
        """
        if artifact_content is None:
            if sys.platform == "darwin":
                artifact_content = _make_darwin_app_zip(version)
            else:
                artifact_content = b"fake-sculptor-artifact-for-testing"

        filename = _artifact_filename(version)
        sha512 = base64.b64encode(hashlib.sha512(artifact_content).digest()).decode()
        release_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        manifest = "\n".join(
            [
                f"version: {version}",
                "files:",
                f"  - url: {filename}",
                f"    sha512: {sha512}",
                f"    size: {len(artifact_content)}",
                f"releaseDate: {release_date}",
                "",
            ]
        )

        with self._state.lock:
            self._state.manifest_yaml = manifest
            self._state.artifact_content = artifact_content
            self._state.artifact_filename = filename
            self._state.artifact_chunk_delay = artifact_chunk_delay

    def set_no_update(self, current_version: str = "0.0.0") -> None:
        """Configure the server to report that the current version is the latest."""
        self.set_update(current_version, b"no-download-expected")

    def set_update_missing_artifact(self, version: str) -> None:
        """Advertise ``version`` but 404 artifact downloads.

        The manifest is valid, but the artifact filename is set to a sentinel
        that will never match a real request, causing ``electron-updater`` to
        receive a 404 and emit an ``error`` event.
        """
        self.set_update(version)
        with self._state.lock:
            self._state.artifact_filename = "__missing__"

    def set_offline(self) -> None:
        """Make the server return 503 for all requests."""
        with self._state.lock:
            self._state.is_offline = True

    def set_online(self) -> None:
        """Restore normal request handling after :meth:`set_offline`."""
        with self._state.lock:
            self._state.is_offline = False

    def get_request_paths(self) -> list[str]:
        """Return a copy of all request paths received so far."""
        with self._state.lock:
            return list(self._state.request_paths)

    def get_request_user_agents(self) -> list[str]:
        """Return a copy of the ``User-Agent`` header from each received request.

        Indexed in lockstep with :meth:`get_request_paths` — the *n*-th entry
        here is the User-Agent of the *n*-th recorded request.
        """
        with self._state.lock:
            return list(self._state.request_user_agents)

    def clear_request_paths(self) -> None:
        """Clear all recorded request state (paths and User-Agents)."""
        with self._state.lock:
            self._state.request_paths.clear()
            self._state.request_user_agents.clear()


@pytest.fixture(scope="session")
def auto_update_server() -> Generator[AutoUpdateTestServer]:
    """Session-scoped local HTTP server for auto-update Electron tests."""
    port_manager = PortManager()
    port = port_manager.get_free_port()
    server = AutoUpdateTestServer(port)
    # Default to "no update" so the Electron app's initial check is harmless.
    server.set_no_update()
    server.start()
    yield server
    server.stop()
    port_manager.release_port(port)
    port_manager.close()
