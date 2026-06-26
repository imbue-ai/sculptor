"""End-to-end auth test for SCU-1441: the stream WebSocket must enforce the
session token.

Spins up a real Sculptor backend (via the shared ``sculptor_instance_factory_``
machinery) with ``SESSION_TOKEN`` set, then connects to ``/api/v1/stream/ws``
the way the ``sculpt`` CLI does — single-shot: connect, read the initial frame,
disconnect. It connects twice against the same backend:

1. with no token, simulating a drive-by page that cannot obtain it — the
   handshake must be rejected with close code 4401; and
2. with the correct token — the handshake succeeds and the initial state dump
   is delivered.

Before SCU-1441 the middleware passed every non-HTTP scope straight through, so
step 1 would have succeeded and streamed all tasks/projects to an unauthorized
client.

Uses the factory fixture rather than hand-rolling backend startup so that
process spawn, readiness, port allocation, and teardown stay consistent with
the rest of the suite across launch modes. The WebSocket client is the
``websockets`` sync client (no event loop of our own); the offload runner
dispatches each test under its own loop, so an ``async def`` test would fail
with "This event loop is already running".
"""

from websockets.exceptions import ConnectionClosed
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect as ws_connect

from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.backend_contract import WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE

_SESSION_TOKEN = "integration-test-secret-token"
# Generous, matching the sculpt CLI's own initial-dump wait — the backend
# emits the first stream frame shortly after the handshake.
_CONNECT_TIMEOUT_SECONDS = 30.0


def _stream_ws_url(base_url: str, *, token: str | None) -> str:
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    url = f"{ws_base}/api/v1/stream/ws"
    if token is not None:
        url = f"{url}?x-session-token={token}"
    return url


def _connect_outcome(url: str) -> tuple[str, object]:
    """Connect single-shot.

    Returns ``("rejected", close_code)`` if the server closes/denies the
    handshake, or ``("accepted", first_frame)`` if a frame is received.
    """
    try:
        with ws_connect(url, max_size=None, open_timeout=_CONNECT_TIMEOUT_SECONDS) as ws:
            frame = ws.recv(timeout=_CONNECT_TIMEOUT_SECONDS)
            return ("accepted", frame)
    except ConnectionClosed as e:
        return ("rejected", e.code)
    except InvalidStatus as e:
        return ("rejected", e.response.status_code)


def test_stream_websocket_requires_session_token(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    # Start the backend with a session token configured so the middleware
    # actually enforces it (the default test environment leaves it unset).
    sculptor_instance_factory_.update_environment(SESSION_TOKEN=_SESSION_TOKEN)
    with sculptor_instance_factory_.spawn_instance() as instance:
        base_url = instance.backend_api_url

        # 1. No token: a drive-by client can't authenticate, so the handshake
        #    must be rejected with the dedicated 4401 close code.
        outcome, detail = _connect_outcome(_stream_ws_url(base_url, token=None))
        assert outcome == "rejected", f"Expected rejection without a token, got {outcome}: {detail!r}"
        assert detail == WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE, (
            f"Expected close code {WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE}, got {detail!r}"
        )

        # 2. Correct token: the handshake succeeds and the initial dump arrives.
        outcome, detail = _connect_outcome(_stream_ws_url(base_url, token=_SESSION_TOKEN))
        assert outcome == "accepted", f"Expected acceptance with the token, got {outcome}: {detail!r}"
