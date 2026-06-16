"""Unit tests for SessionTokenMiddleware.

Includes a regression test for SCU-703: a client disconnect during an
in-flight request must not raise `RuntimeError("No response returned.")`.
That error is specific to `BaseHTTPMiddleware`'s anyio-bridge design and
caused integration-test flakes whenever Playwright's `full_spa_reload`
cancelled in-flight asset fetches.
"""

import pytest
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.types import Message
from starlette.types import Scope
from starlette.websockets import WebSocketDisconnect

from sculptor.config.settings import SculptorSettings
from sculptor.web.auth import SESSION_TOKEN_HEADER_NAME
from sculptor.web.auth import SessionTokenMiddleware
from sculptor.web.auth import WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE


def _settings_no_token() -> SculptorSettings:
    return SculptorSettings(SESSION_TOKEN=None)


def _settings_with_token() -> SculptorSettings:
    return SculptorSettings(SESSION_TOKEN=SecretStr("secret123"))


def _make_app(settings_factory) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionTokenMiddleware, settings_factory=settings_factory)

    @app.get("/api/v1/items")
    def items() -> dict:
        return {"items": []}

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/non-api")
    def non_api() -> dict:
        return {"page": "home"}

    @app.options("/api/v1/items")
    def options() -> dict:
        return {}

    @app.websocket("/api/v1/stream/ws")
    async def stream_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"ok": True})
        await websocket.close()

    return app


def test_no_token_configured_passes_all_requests() -> None:
    """When SESSION_TOKEN is unset, the middleware is a pass-through."""
    client = TestClient(_make_app(_settings_no_token))
    assert client.get("/api/v1/items").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/non-api").status_code == 200


def test_protected_route_requires_token() -> None:
    client = TestClient(_make_app(_settings_with_token))

    # Missing -> 403 with structured error code.
    r = client.get("/api/v1/items")
    assert r.status_code == 403
    assert r.json() == {"detail": "Invalid or missing session token"}
    assert r.headers.get("x-error-code") == "invalid_session_token"

    # Wrong -> 403.
    assert client.get("/api/v1/items", headers={SESSION_TOKEN_HEADER_NAME: "wrong"}).status_code == 403


def test_token_accepted_via_header_query_or_cookie() -> None:
    app = _make_app(_settings_with_token)
    assert TestClient(app).get("/api/v1/items", headers={SESSION_TOKEN_HEADER_NAME: "secret123"}).status_code == 200
    assert TestClient(app).get(f"/api/v1/items?{SESSION_TOKEN_HEADER_NAME}=secret123").status_code == 200
    cookie_client = TestClient(app, cookies={SESSION_TOKEN_HEADER_NAME: "secret123"})
    assert cookie_client.get("/api/v1/items").status_code == 200


def test_exempt_paths_and_options_and_non_api_bypass_check() -> None:
    client = TestClient(_make_app(_settings_with_token))
    # /api/v1/health is exempt.
    assert client.get("/api/v1/health").status_code == 200
    # Non-API paths are not gated.
    assert client.get("/non-api").status_code == 200
    # OPTIONS preflight passes through so CORS can answer.
    assert client.options("/api/v1/items").status_code == 200


def test_dependency_overrides_are_honored() -> None:
    """The middleware must consult `app.dependency_overrides` so test setups
    can swap the settings factory without rebuilding the middleware stack."""
    app = _make_app(_settings_with_token)
    app.dependency_overrides[_settings_with_token] = _settings_no_token
    client = TestClient(app)
    # Override returns SESSION_TOKEN=None -> no check is performed.
    assert client.get("/api/v1/items").status_code == 200


def test_websocket_requires_token() -> None:
    """SCU-1441: a WebSocket handshake with no token must be rejected.

    Previously every non-HTTP scope was passed straight through, so the stream
    and terminal WebSockets were reachable with no token at all.
    """
    client = TestClient(_make_app(_settings_with_token))
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/stream/ws") as ws:
            ws.receive_json()
    assert exc_info.value.code == WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE


def test_websocket_rejects_wrong_token() -> None:
    client = TestClient(_make_app(_settings_with_token))
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/stream/ws?{SESSION_TOKEN_HEADER_NAME}=wrong") as ws:
            ws.receive_json()
    assert exc_info.value.code == WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE


def test_websocket_accepts_token_via_query_param() -> None:
    client = TestClient(_make_app(_settings_with_token))
    with client.websocket_connect(f"/api/v1/stream/ws?{SESSION_TOKEN_HEADER_NAME}=secret123") as ws:
        assert ws.receive_json() == {"ok": True}


def test_websocket_accepts_token_via_cookie() -> None:
    """Direct-browser (non-Electron) clients carry the token as a SameSite cookie."""
    client = TestClient(_make_app(_settings_with_token), cookies={SESSION_TOKEN_HEADER_NAME: "secret123"})
    with client.websocket_connect("/api/v1/stream/ws") as ws:
        assert ws.receive_json() == {"ok": True}


def test_websocket_passes_through_when_no_token_configured() -> None:
    client = TestClient(_make_app(_settings_no_token))
    with client.websocket_connect("/api/v1/stream/ws") as ws:
        assert ws.receive_json() == {"ok": True}


async def test_client_disconnect_does_not_raise_no_response_returned() -> None:
    """SCU-703 regression: a client that disconnects before the inner app
    sends a response must not surface as `RuntimeError("No response returned.")`.

    That error is `BaseHTTPMiddleware.call_next`'s failure mode (Starlette
    issue #1438): the anyio-bridge design treats a graceful inner-app exit
    with no `http.response.start` as a server-side bug. A pure ASGI
    middleware has no such bridge — the same input simply propagates as a
    normal task completion.
    """

    async def inner_app_that_sees_disconnect(scope: Scope, receive, send) -> None:
        # Reads the disconnect message and exits without sending a response,
        # mirroring how a static-file or route handler can exit when the
        # client cancels mid-request.
        msg = await receive()
        assert msg["type"] == "http.disconnect"

    middleware = SessionTokenMiddleware(inner_app_that_sees_disconnect, settings_factory=_settings_no_token)
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/items",
        "headers": [],
        "query_string": b"",
    }

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    sent_messages: list[Message] = []

    async def send(message: Message) -> None:
        sent_messages.append(message)

    await middleware(scope, receive, send)
    assert sent_messages == []
