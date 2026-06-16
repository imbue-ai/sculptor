"""HTTP server that serves a small static site for Browser panel integration tests.

Used to drive navigation, cookie, and popup behavior in the Electron
``<webview>`` without relying on external network access.
"""

from __future__ import annotations

import functools
import http.server
import random
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ConfigDict

from sculptor.foundation.pydantic_serialization import FrozenModel

FIXTURE_PAGES_DIR: Path = Path(__file__).parent / "browser_panel_fixture_pages"

# Bind inside the IANA dynamic/private range, which sits above every entry in
# Chromium's unsafe-ports list (max 10080) and inside the ephemeral pools used
# by both macOS and Linux — so the OS won't hand out the same port to another
# process mid-test, and Chromium will load whatever we pick.
_SAFE_PORT_MIN: int = 49152
_SAFE_PORT_MAX: int = 60999

_MAX_PORT_RETRIES: int = 8

_THREAD_JOIN_TIMEOUT_SECONDS: float = 2.0


class BrowserPanelFixtureServer(FrozenModel):
    # The server and thread are live runtime objects with no serializable form,
    # so this immutable container must allow arbitrary field types.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_url: str
    port: int
    server: http.server.HTTPServer
    thread: threading.Thread

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)


def _build_handler_class() -> type[http.server.SimpleHTTPRequestHandler]:
    # Bind `directory` via functools.partial so we do not need a subclass
    # with an `__init__(*args, **kwargs)` signature.
    handler_cls: type[http.server.SimpleHTTPRequestHandler] = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(FIXTURE_PAGES_DIR),
    )  # pyright: ignore[reportAssignmentType]
    return handler_cls


def _start_server() -> BrowserPanelFixtureServer:
    handler_cls = _build_handler_class()
    for _attempt in range(_MAX_PORT_RETRIES):
        port = random.randint(_SAFE_PORT_MIN, _SAFE_PORT_MAX)
        try:
            server = http.server.HTTPServer(("127.0.0.1", port), handler_cls)
        except OSError:
            continue
        thread = threading.Thread(target=server.serve_forever, name="browser-panel-fixture", daemon=True)
        thread.start()
        return BrowserPanelFixtureServer(
            base_url=f"http://127.0.0.1:{port}",
            port=port,
            server=server,
            thread=thread,
        )
    raise RuntimeError(
        f"Could not bind a port in [{_SAFE_PORT_MIN}, {_SAFE_PORT_MAX}] after {_MAX_PORT_RETRIES} attempts"
    )


@pytest.fixture(scope="function")
def browser_panel_fixture_server_() -> Iterator[BrowserPanelFixtureServer]:
    server = _start_server()
    try:
        yield server
    finally:
        server.shutdown()
