"""Report terminal-agent integration signals to Sculptor.

Thin wrappers over POST /api/v1/agents/{agent_id}/signal so shell-based
hooks never hand-roll HTTP. Invoked from hooks on every state transition —
the happy path stays silent and the imports stay light.
"""

import json
import os
import time
from typing import Any

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client import Client
from sculpt.client.api.default import post_agent_signal
from sculpt.client.models.signal_event_request import SignalEventRequest
from sculpt.client.types import Response
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

signal_app = typer.Typer(help="Report terminal-agent integration signals to Sculptor.")

_AGENT_OPTION = typer.Option(None, "--agent", help="Agent ID (or set SCULPT_AGENT_ID)")
_JSON_OPTION = typer.Option(False, "--json", help="Output as JSON")

# A registered terminal agent reports its session id from a hook; a dropped report
# means it relaunches instead of resuming after a backend restart, so the report is
# worth retrying. Other signals are momentary state pings that self-correct on the
# next transition, so they post once.
_SESSION_ID_MAX_ATTEMPTS = 5
_RETRY_BACKOFF_SECONDS = 0.5
_RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError)


def _resolve_agent_id(agent: str | None, json_output: bool) -> str:
    agent_id = agent or os.environ.get("SCULPT_AGENT_ID")
    if not agent_id:
        cli_error(
            "No agent ID provided",
            detail="Pass --agent or set SCULPT_AGENT_ID — not running inside a Sculptor terminal agent?",
            json_output=json_output,
        )
    return agent_id


def _post_signal_with_retries(
    client: Client, agent_id: str, body: SignalEventRequest, max_attempts: int
) -> Response[Any] | None:
    """POST the signal, retrying transient failures with a short linear backoff.

    Retries on connect/read timeouts, a refused connection, and 5xx responses;
    a non-5xx response (success or a permanent 4xx) ends the loop immediately.
    Returns the last response the backend returned, or None when every attempt
    failed before the backend answered.
    """
    response: Response[Any] | None = None
    for attempt in range(max_attempts):
        try:
            attempt_response = post_agent_signal.sync_detailed(agent_id=agent_id, client=client, body=body)
        except _RETRYABLE_EXCEPTIONS:
            attempt_response = None
        if attempt_response is not None:
            response = attempt_response
            if int(response.status_code) < 500:
                return response
        if attempt + 1 < max_attempts:
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
    return response


def _post_event(
    event: str, agent: str | None, json_output: bool, session_id: str | None = None, *, max_attempts: int = 1
) -> None:
    """POST one signal event; 204 is silent success, anything else exits 1."""
    agent_id = _resolve_agent_id(agent, json_output)
    client = get_authenticated_client(get_default_base_url())
    body = SignalEventRequest(event=event) if session_id is None else SignalEventRequest(event=event, session_id=session_id)
    response = _post_signal_with_retries(client, agent_id, body, max_attempts)
    if response is None:
        handle_connection_error(json_output)
    if int(response.status_code) != 204:
        cli_error(
            f"Signal '{event}' failed with status {int(response.status_code)}",
            detail=response.content.decode(errors="replace"),
            json_output=json_output,
        )
    if json_output:
        typer.echo(json.dumps({"ok": True}))


@signal_app.command("busy")
def busy(agent: str = _AGENT_OPTION, json_output: bool = _JSON_OPTION) -> None:
    """Signal that the agent's program is actively working."""
    _post_event("busy", agent, json_output)


@signal_app.command("idle")
def idle(agent: str = _AGENT_OPTION, json_output: bool = _JSON_OPTION) -> None:
    """Signal that the agent's program is idle."""
    _post_event("idle", agent, json_output)


@signal_app.command("waiting")
def waiting(agent: str = _AGENT_OPTION, json_output: bool = _JSON_OPTION) -> None:
    """Signal that the agent's program is waiting on user input."""
    # CLI surface uses the short form; the wire uses the spec's full name.
    _post_event("waiting-on-input", agent, json_output)


@signal_app.command("files-changed")
def files_changed(agent: str = _AGENT_OPTION, json_output: bool = _JSON_OPTION) -> None:
    """Signal that files in the workspace changed (refreshes the diff)."""
    _post_event("files-changed", agent, json_output)


@signal_app.command("session-id")
def session_id(
    session_id: str = typer.Argument(..., help="The program's session id, for resume after restart"),
    agent: str = _AGENT_OPTION,
    json_output: bool = _JSON_OPTION,
) -> None:
    """Report the program's session id so Sculptor can resume it after a restart."""
    _post_event("session-id", agent, json_output, session_id=session_id, max_attempts=_SESSION_ID_MAX_ATTEMPTS)
