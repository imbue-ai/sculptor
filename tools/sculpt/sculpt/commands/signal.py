"""Report terminal-agent integration signals to Sculptor (REQ-SIG-3).

Thin wrappers over POST /api/v1/agents/{agent_id}/signal so shell-based
hooks never hand-roll HTTP. Invoked from hooks on every state transition —
the happy path stays silent and the imports stay light.
"""

import json
import os

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client.api.default import post_agent_signal
from sculpt.client.models.signal_event_request import SignalEventRequest
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

signal_app = typer.Typer(help="Report terminal-agent integration signals to Sculptor.")

_AGENT_OPTION = typer.Option(None, "--agent", help="Agent ID (or set SCULPT_AGENT_ID)")
_JSON_OPTION = typer.Option(False, "--json", help="Output as JSON")


def _resolve_agent_id(agent: str | None, json_output: bool) -> str:
    agent_id = agent or os.environ.get("SCULPT_AGENT_ID")
    if not agent_id:
        cli_error(
            "No agent ID provided",
            detail="Pass --agent or set SCULPT_AGENT_ID — not running inside a Sculptor terminal agent?",
            json_output=json_output,
        )
    return agent_id


def _post_event(event: str, agent: str | None, json_output: bool, session_id: str | None = None) -> None:
    """POST one signal event; 204 is silent success, anything else exits 1."""
    agent_id = _resolve_agent_id(agent, json_output)
    client = get_authenticated_client(get_default_base_url())
    body = SignalEventRequest(event=event) if session_id is None else SignalEventRequest(event=event, session_id=session_id)
    try:
        response = post_agent_signal.sync_detailed(agent_id=agent_id, client=client, body=body)
    except (httpx.ConnectError, httpx.ConnectTimeout):
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
    _post_event("session-id", agent, json_output, session_id=session_id)
