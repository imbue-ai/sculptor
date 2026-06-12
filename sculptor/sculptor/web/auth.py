"""
Session token middleware for CSRF protection.

Third-party web pages could in theory send POST requests to our API endpoints when Sculptor runs on localhost.
We prevent that using the SessionTokenMiddleware, which requires a shared session token to be sent in a custom header.
The session token is generated when the Electron app starts.

"""

from contextlib import contextmanager
from typing import Callable
from typing import Generator

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import EmailStr
from starlette import status
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send
from starlette.websockets import WebSocket

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import UserSettings
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.constants import ANONYMOUS_USER_REFERENCE
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction

ANONYMOUS_USER_EMAIL = "_anonymous@imbue.com"


class UserSession(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
    )

    user_reference: UserReference
    user_settings: UserSettings
    user_email: EmailStr
    # A session is always scoped to a single organization.
    organization_reference: OrganizationReference
    request_id: RequestID
    logger_kwargs: dict[str, str]

    @contextmanager
    def open_transaction(
        self,
        services: CompleteServiceCollection,
        *,
        immediate: bool = False,
    ) -> Generator[DataModelTransaction, None, None]:
        """Open a SQL transaction scoped to this user session.

        Pass ``immediate=True`` for read-then-write endpoints where a stale
        snapshot could revive a concurrently-deleted row (SCU-168).
        """
        with services.data_model_service.open_transaction(self.request_id, immediate=immediate) as transaction:
            yield transaction

    @contextmanager
    def contextualize(self) -> Generator[None, None, None]:
        with logger.contextualize(**self.logger_kwargs):
            yield

    @property
    def is_anonymous(self) -> bool:
        return self.user_reference == ANONYMOUS_USER_REFERENCE


def authenticate_anonymous(services: CompleteServiceCollection, request_id: RequestID) -> UserSession:
    """
    Create an anonymous user session.

    """
    user_email = ANONYMOUS_USER_EMAIL
    organization_reference = ANONYMOUS_ORGANIZATION_REFERENCE
    user_reference = ANONYMOUS_USER_REFERENCE
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        user_settings = transaction.get_or_create_user_settings(user_reference)
    return UserSession(
        user_reference=user_reference,
        user_settings=user_settings,
        user_email=user_email,
        organization_reference=organization_reference,
        request_id=request_id,
        logger_kwargs={},
    )


SESSION_TOKEN_HEADER_NAME = "x-session-token"
# WebSocket close code used when the handshake is rejected for a bad/missing
# session token. 4401 mirrors HTTP 401 in the application-private 4000-4999
# range; we accept-then-close (rather than denying pre-accept) so the browser
# receives this as a real close frame instead of an opaque 1006.
WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE = 4401
SESSION_TOKEN_PROTECTED_API_PREFIXES = ["/api/"]
SESSION_TOKEN_EXEMPT_PATHS = [
    "/api/v1/health",  # Used to determine if the server is up at all.
    "/api/v1/session-token",
    # Developer-only tracing endpoint. Only accepts events when the
    # --trace-to flag is set (which gates whether anything is buffered
    # at all); when the flag is off the endpoint silently no-ops. We
    # exempt it from session-token auth because Electron main runs in a
    # separate process with no shared cookie jar with the renderer, and
    # the simplest cross-process path is "no auth on this dev-only
    # endpoint." See docs/development/tracing.md for the security implications.
    "/api/v1/trace/batch",
]


class SessionTokenMiddleware:
    """
    When enabled, refuse any requests that do not have the correct session token in the `X-Session-Token` header.

    Enable this by setting the SculptorSettings.SESSION_TOKEN variable.

    The purpose is to prevent unauthorized access to the API (csrf and similar attacks).

    Implemented as a pure ASGI middleware rather than a `BaseHTTPMiddleware`
    subclass: BaseHTTPMiddleware wraps the inner app in an anyio TaskGroup,
    and a client disconnect mid-request surfaces inside that TaskGroup as
    `RuntimeError("No response returned.")` — which Starlette's error
    middleware logs at ERROR level (Starlette issue #1438). Integration
    tests treat any ERROR log as a failure (SCU-703), and Playwright's
    `full_spa_reload` routinely cancels in-flight asset fetches, so the
    BaseHTTPMiddleware variant produced spurious flakes. Pure ASGI
    middleware doesn't introduce a TaskGroup and therefore doesn't have
    this race.
    """

    def __init__(self, app: ASGIApp, settings_factory: Callable[[], SculptorSettings]) -> None:
        self.app = app
        self.settings_factory = settings_factory

    def _get_session_token(self, scope: Scope) -> str | None:
        starlette_app = scope.get("app")
        factory = self.settings_factory
        if starlette_app is not None:
            factory = starlette_app.dependency_overrides.get(self.settings_factory, self.settings_factory)
        return factory().SESSION_TOKEN

    @staticmethod
    def _is_protected_path(path: str) -> bool:
        if path in SESSION_TOKEN_EXEMPT_PATHS:
            return False
        return any(path.startswith(prefix) for prefix in SESSION_TOKEN_PROTECTED_API_PREFIXES)

    @staticmethod
    def _has_valid_token(connection: HTTPConnection, expected_token: str) -> bool:
        # The token may arrive in the custom header (normal HTTP from Electron),
        # a query parameter (EventSources / WebSockets, which can't set custom
        # headers), or a SameSite cookie (direct browser access without Electron).
        header_token = connection.headers.get(SESSION_TOKEN_HEADER_NAME)
        query_token = connection.query_params.get(SESSION_TOKEN_HEADER_NAME)
        cookie_token = connection.cookies.get(SESSION_TOKEN_HEADER_NAME)
        return expected_token in (header_token, query_token, cookie_token)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        expected_token = self._get_session_token(scope)
        if expected_token is None:
            await self.app(scope, receive, send)
            return

        # Allow CORS preflight requests through so the CORSMiddleware can
        # respond with the appropriate Access-Control-* headers.
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope)
        if not self._is_protected_path(request.url.path):
            await self.app(scope, receive, send)
            return

        if not self._has_valid_token(request, expected_token):
            response = JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid or missing session token"},
                headers={"x-error-code": "invalid_session_token"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    async def _handle_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce the session token on WebSocket handshakes.

        Without this, ``__call__`` previously passed every non-HTTP scope
        straight through, so the token was never checked on WebSockets even
        when set (SCU-1441). The stream WS (full-data exfil) and terminal WS
        (interactive host shell) were therefore reachable with no token by any
        page the user merely visited while Sculptor was running.
        """
        expected_token = self._get_session_token(scope)
        if expected_token is None:
            await self.app(scope, receive, send)
            return

        websocket = WebSocket(scope=scope, receive=receive, send=send)
        if not self._is_protected_path(websocket.url.path):
            await self.app(scope, receive, send)
            return

        if not self._has_valid_token(websocket, expected_token):
            # Accept then close so the browser sees a real 4401 close frame
            # rather than an opaque 1006 (the same reason the terminal route
            # accepts before sending its 4404). No data is relayed before the
            # close, so accepting the unauthorized socket leaks nothing.
            await websocket.accept()
            await websocket.close(
                code=WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE,
                reason="Invalid or missing session token",
            )
            return

        await self.app(scope, receive, send)
