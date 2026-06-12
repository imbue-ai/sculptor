"""Session token handling for the Sculptor API."""

from http import HTTPStatus

from sculpt.client import Client
from sculpt.client.api.default import set_session_token_cookie


class SessionTokenError(Exception):
    """Raised when session token retrieval fails."""


def get_session_token(client: Client) -> str:
    """Get a session token from the Sculptor API.

    The session token is returned as a cookie from /api/v1/session-token.
    This function extracts the token from the response cookies.

    Args:
        client: The API client to use.

    Returns:
        The session token string.

    Raises:
        SessionTokenError: If the token could not be retrieved.
    """
    response = set_session_token_cookie.sync_detailed(client=client)

    if response.status_code != HTTPStatus.NO_CONTENT:
        raise SessionTokenError(f"Failed to get session token: unexpected status {response.status_code}")

    # The token is in the Set-Cookie header as "x-session-token=<value>"
    set_cookie_header = response.headers.get("set-cookie", "")
    for part in set_cookie_header.split(";"):
        part = part.strip()
        if part.startswith("x-session-token="):
            return part.split("=", 1)[1]

    raise SessionTokenError("Failed to get session token: x-session-token cookie not found in response")
