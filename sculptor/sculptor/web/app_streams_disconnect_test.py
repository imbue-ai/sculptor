"""Tests for how the unified stream treats a browser that has already closed its connection.

uvicorn raises `ClientDisconnected` from any send to a client that has gone,
including the handshake's accept. A browser that closes its socket while the
server is still accepting it, or before the server closes it on shutdown, has
closed normally, so the stream must return quietly: anything it raises reaches
uvicorn as "Exception in ASGI application", logged at ERROR.
"""

from threading import Event
from typing import Generator

from starlette.types import Message
from starlette.types import Scope
from starlette.websockets import WebSocket
from uvicorn.protocols.utils import ClientDisconnected

from sculptor.database.models import UserSettings
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.constants import ANONYMOUS_USER_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserSettingsID
from sculptor.web.app import to_websocket_stream
from sculptor.web.auth import ANONYMOUS_USER_EMAIL
from sculptor.web.auth import UserSession

_STREAM_SCOPE: Scope = {"type": "websocket", "path": "/api/v1/stream/ws", "headers": [], "query_string": b""}


def _anonymous_user_session() -> UserSession:
    return UserSession(
        user_reference=ANONYMOUS_USER_REFERENCE,
        user_settings=UserSettings(object_id=UserSettingsID(), user_reference=ANONYMOUS_USER_REFERENCE),
        user_email=ANONYMOUS_USER_EMAIL,
        organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
        request_id=RequestID(),
        logger_kwargs={},
    )


async def _receive_connect() -> Message:
    return {"type": "websocket.connect"}


async def _send_to_departed_client(message: Message) -> None:
    raise ClientDisconnected()


def _updates_never_read() -> Generator[None, None, None]:
    raise AssertionError("the stream must not be read for a client that is already gone")
    yield


async def test_stream_returns_quietly_when_client_leaves_before_accept() -> None:
    websocket = WebSocket(_STREAM_SCOPE, receive=_receive_connect, send=_send_to_departed_client)

    await to_websocket_stream(_anonymous_user_session(), _updates_never_read(), websocket, Event())
