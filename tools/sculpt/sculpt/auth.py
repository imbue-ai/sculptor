"""Authentication and shared configuration for the sculpt CLI."""

import os

import httpx
import typer

from sculpt.client import Client
from sculpt.client.models import LLMModel
from sculpt.formatting import CONNECTION_HINT
from sculpt.session import SessionTokenError
from sculpt.session import get_session_token

DEFAULT_PORT = 5050

# httpx silently defaults to a 5s request timeout, which a momentarily slow local
# backend can exceed, dropping the request. Pin a longer, explicit ceiling so
# transient slowness isn't mistaken for failure.
_HTTP_TIMEOUT_SECONDS = 30.0


def get_default_base_url() -> str:
    """Get the default base URL, respecting SCULPT_API_PORT if set."""
    port = os.environ.get("SCULPT_API_PORT", str(DEFAULT_PORT))
    return f"http://localhost:{port}"


def build_client(base_url: str) -> Client:
    """Build a sculpt API client with an explicit, generous request timeout."""
    return Client(base_url=base_url, timeout=httpx.Timeout(_HTTP_TIMEOUT_SECONDS))


MODEL_MAPPING: dict[str, LLMModel] = {
    "haiku": LLMModel.CLAUDE_4_HAIKU,
    "sonnet": LLMModel.CLAUDE_4_SONNET_200K,
    "sonnet[1m]": LLMModel.CLAUDE_4_SONNET,
    "opus": LLMModel.CLAUDE_4_OPUS_200K,
    "opus[1m]": LLMModel.CLAUDE_4_OPUS,
    "fable": LLMModel.CLAUDE_FABLE_5,
}


def get_authenticated_client(base_url: str) -> Client:
    """Create an authenticated client for the Sculptor API."""
    client = build_client(base_url)
    try:
        session_token = get_session_token(client)
    except SessionTokenError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except (httpx.ConnectError, httpx.ConnectTimeout):
        typer.echo(f"Error: Could not connect to Sculptor server at {base_url}", err=True)
        typer.echo(CONNECTION_HINT, err=True)
        raise typer.Exit(code=1) from None
    return client.with_headers({"x-session-token": session_token})
