"""
We use Authentik for authentication and authorization.

The Authentik server runs here: https://auth.imbue.com/
For now, we share the same auth provider across all environments.

It works like this:
    - The access to API endpoints is protected by checking for a valid Json Web Token (JWT) in the Authorization header.
    - When the ALLOW_ANONYMOUS_USERS env var is true, we default to an anonymous user session.
    - Otherwise, we return http 401 Unauthorized if no JWT is provided.
    - The frontend notices this and redirects the user to the /login endpoint.
    - From there, the OAuth2 + PKCE flow is initiated, which redirects the user to Authentik.
    - After the user authenticates, Authentik redirects back to the /auth/callback endpoint with a code.
    - The callback endpoint exchanges the code for an access token and a refresh token.
    - Then the user gets redirected back to the frontend with JWT in a ?jwt= query parameter.
    - The frontend saves the token in local storage (under the `sculptor-jwt` key) and uses it for subsequent requests.
    - The refresh token is saved in a secure http-only cookie.
    - Next time http 401 or 403 is received, the frontend will try to refresh the tokens using the refresh token cookie.
      (Using the /renew-tokens endpoint.)

For now, the only way to register in Authentik is by manually creating a user in the admin interface
(See the Management section in the Authentik readme at ../../../authentik/README.md.)

When anonymous users are allowed, third-party web pages could in theory send POST requests to our API endpoints even when Sculptor runs on localhost.
We prevent that using the AppSecretMiddleware, which requires a shared app secret to be sent in a custom header.
The app secret is generated when the Electron app starts.

"""

import base64
import hashlib
import secrets
import time
import urllib.parse
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from threading import Lock
from typing import Callable
from typing import Generator
from typing import cast
from urllib.parse import urljoin

import httpx
import jwt
import pydantic
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import algorithms
from loguru import logger
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import EmailStr
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from imbue_core.pydantic_serialization import MutableModel
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import UserSettings
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.constants import ANONYMOUS_USER_REFERENCE
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import get_deterministic_typeid_suffix
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction

# For now, let's use a generous expiry time of 180 days.
# (Once we have actual workflows for token refreshing, we should reduce this to a day or two.)
# (For now, this should be fine because we should rotate the private key before doing a wider public release, anyway.)
DEFAULT_EXPIRY_TIME_SECONDS = 60 * 60 * 24 * 180
# FIXME(a2fde9bd-7aba-4d1a-aaab-04f7ba35ba1f): replace this with the test key, which already exists in keys/  See other FIXME with the same ID
DEFAULT_PRIVATE_KEY_PATH = Path(__file__).parent.parent.parent / "science" / "secrets" / "crafty" / "private.pem"

ANONYMOUS_USER_EMAIL = "_anonymous@imbue.com"
AUTHENTIK_SCOPE = "openid email profile offline_access organizations"


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
    def open_transaction(self, services: CompleteServiceCollection) -> Generator[DataModelTransaction, None, None]:
        with services.data_model_service.open_transaction(self.request_id) as transaction:
            yield transaction

    @contextmanager
    def contextualize(self) -> Generator[None, None, None]:
        with logger.contextualize(**self.logger_kwargs):
            yield

    @property
    def is_anonymous(self) -> bool:
        return self.user_reference == ANONYMOUS_USER_REFERENCE


# TODO: we can remove this as well once we have proper user management.
#  for now it just helps prevent tests from accidentally creating errors when simmultaneous requests try to create the same user.
_DEFAULT_USER_CREATION_LOCK = Lock()


def authenticate(
    json_web_token: str,
    services: CompleteServiceCollection,
    request_id: RequestID,
) -> UserSession:
    """
    Use the Json Web Token to authenticate the user.

    """
    try:
        key_id = jwt.get_unverified_header(json_web_token).get("kid")
    except jwt.PyJWTError:
        raise InvalidTokenError("Could not validate credentials.")
    public_key = get_public_key(services.settings, key_id=key_id)
    try:
        payload = jwt.decode(
            json_web_token,
            public_key,
            algorithms=["RS256"],
            options={
                # It's easier to not verify audience at the moment and there's no good reason to do so, anyway.
                "verify_aud": False,
            },
        )
    except jwt.PyJWTError as e:
        logger.debug(e)
        raise InvalidTokenError("Could not validate credentials.") from e

    if not _is_token_payload_complete(payload):
        raise InvalidTokenError("Missing required claims in token payload.")
    user_email = payload["sub"]
    user_reference = UserReference(payload["usr"])
    # TODO: Deal with the user being a member of more than one organization.
    organization_reference = OrganizationReference(payload["org"][0])
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        user_settings = transaction.get_or_create_user_settings(user_reference)

    return UserSession(
        user_reference=user_reference,
        user_email=user_email,
        user_settings=user_settings,
        organization_reference=organization_reference,
        request_id=request_id,
        logger_kwargs={},
    )


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


@cache
def _read_key(key_path: str) -> str:
    return Path(key_path).read_text()


def _is_token_payload_complete(payload: dict) -> bool:
    """
    Check if a JWT token payload contains all required claims for authentication.

    """
    if not all(claim in payload for claim in ("sub", "usr", "org")):
        return False
    # The "organizations" custom property mapping defined if Authentik should make sure
    # that there's always at least the user's personal organization.
    return len(payload["org"]) > 0


def create_test_token(
    user_email: str,
    organization_reference: str,
    expiry_time_seconds: int = DEFAULT_EXPIRY_TIME_SECONDS,
    private_key_path: Path = DEFAULT_PRIVATE_KEY_PATH,
) -> str:
    """
    Create a test token for the given user email.

    (In production, we delegate get tokens from Authentik.)

    """
    try:
        pydantic.validate_email(user_email)
    except ValueError as e:
        raise InvalidEmailError(f"Invalid email address: {user_email}") from e

    # We use predictable IDs in order to avoid having to regenerate tokens all the time
    # (This may change once we have proper token refresh workflows.)
    user_id = get_deterministic_typeid_suffix(user_email)
    payload = {
        # Standard claims specified in RFC 7519.
        "sub": user_email,
        "usr": user_id,
        "exp": int(time.time()) + expiry_time_seconds,
        "org": [organization_reference],
    }
    return jwt.encode(
        payload,
        private_key_path.read_text(),
        algorithm="RS256",
    )


class InvalidEmailError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


# Helpers for the Authentik OAuth2 flow.
def get_authorization_url(settings: SculptorSettings) -> str:
    authentik_base_url = settings.AUTHENTIK_BASE_URL
    return urljoin(authentik_base_url, "application/o/authorize/")


def get_token_url(settings: SculptorSettings) -> str:
    authentik_base_url = settings.AUTHENTIK_BASE_URL
    return urljoin(authentik_base_url, "application/o/token/")


def get_redirect_url(settings: SculptorSettings) -> str:
    protocol, domain, port = settings.PROTOCOL, settings.DOMAIN, settings.BACKEND_PORT
    return f"{protocol}://{domain}:{port}/api/v1/auth/callback"


def get_logout_url(settings: SculptorSettings, next_url: str) -> str:
    authentik_base_url = settings.AUTHENTIK_BASE_URL
    application_name = settings.AUTHENTIK_APPLICATION_NAME
    # TODO: make the ?next=... part actually work.
    return (
        urljoin(authentik_base_url, f"application/o/{application_name}/end-session/")
        + "?next="
        + urllib.parse.quote(next_url)
    )


def get_jwks_url(settings: SculptorSettings) -> str:
    authentik_base_url = settings.AUTHENTIK_BASE_URL
    application_name = settings.AUTHENTIK_APPLICATION_NAME
    return urljoin(authentik_base_url, f"application/o/{application_name}/jwks/")


def generate_pkce_verifier_challenge_and_state() -> tuple[str, str, str]:
    """
    Returns a triple <state, code_verifier, code_challenge> for PKCE (Proof Key for Code Exchange).
    """
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode("utf-8")
    )
    return state, code_verifier, code_challenge


def get_public_key(settings: SculptorSettings, key_id: str | None = None) -> RSAPublicKey | str:
    if settings.JWT_PUBLIC_KEY_PATH:
        return _read_public_key_from_path(settings.JWT_PUBLIC_KEY_PATH)
    assert key_id is not None, "Key ID must be provided when retrieving public key from Authentik."
    return _retrieve_public_key_from_authentik(get_jwks_url(settings), key_id)


@cache
def _retrieve_public_key_from_authentik(authentik_jwks_url: str, key_id: str) -> RSAPublicKey:
    response = httpx.get(authentik_jwks_url)
    response.raise_for_status()
    data = response.json()
    for key in data["keys"]:
        if key["kid"] == key_id:
            return cast(RSAPublicKey, algorithms.RSAAlgorithm.from_jwk(key))
    raise NoSuchKeyError(f"No key found with ID {key_id} in JWKS at {authentik_jwks_url}")


@cache
def _read_public_key_from_path(public_key_path: str) -> str:
    return Path(public_key_path).read_text()


class NoSuchKeyError(Exception):
    pass


class PKCEStore(MutableModel):
    """
    Store for PKCE verifiers and states.

    This is a simple in-memory store.

    Replace by something else when / if we need to run this in a distributed environment (scalable cloud servers).

    """

    verifier_by_state: dict[str, tuple[str, str]] = pydantic.Field(default_factory=dict)

    def set(self, state: str, verifier: str, next_path: str) -> None:
        self.verifier_by_state[state] = (verifier, next_path)

    def get(self, state: str) -> tuple[str, str] | None:
        return self.verifier_by_state.get(state)

    def delete(self, state: str) -> None:
        try:
            del self.verifier_by_state[state]
        except KeyError:
            pass


PKCE_STORE = PKCEStore()


def get_random_csrf_token() -> str:
    return secrets.token_urlsafe(32)


APP_SECRET_HEADER_NAME = "x-app-secret"


class AppSecretMiddleware(BaseHTTPMiddleware):
    """
    When enabled, refuse any requests that do not have the correct app secret in the `X-App-Secret` header.

    Enable this by setting the SculptorSettings.ELECTRON_APP_SECRET variable.

    The purpose is to prevent unauthorized access to the API (csrf and similar attacks).

    """

    def __init__(self, app, settings_factory: Callable[[], SculptorSettings]):
        super().__init__(app)
        self.settings_factory = settings_factory

    def _get_secret(self, request: Request) -> str | None:
        settings = request.app.dependency_overrides.get(self.settings_factory, self.settings_factory)()
        return settings.ELECTRON_APP_SECRET

    async def dispatch(self, request: Request, call_next: Callable):
        expected_secret = self._get_secret(request)
        if expected_secret is None:
            return await call_next(request)
        header_secret = request.headers.get(APP_SECRET_HEADER_NAME)
        # Support also getting the secret from a query parameter for EventSources / websockets.
        get_param_secret = request.query_params.get(APP_SECRET_HEADER_NAME)
        if header_secret != expected_secret and get_param_secret != expected_secret:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid or missing app secret"},
                headers={"x-error-code": "invalid_app_secret"},
            )
        return await call_next(request)
