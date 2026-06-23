"""Tests for the pi login WebSocket route's 4404 close-frame contract.

The live login round-trip is covered by the real_pi conformance tests; here we
assert that attaching to an unknown login session closes with 4404 (the frontend's
not-found signal), mirroring the agent-terminal WS validation tests.
"""

import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


def test_pi_login_ws_4404_for_unknown_session(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/pi/login/nonexistent/ws") as ws:
            ws.receive_bytes()
    assert exc_info.value.code == 4404
