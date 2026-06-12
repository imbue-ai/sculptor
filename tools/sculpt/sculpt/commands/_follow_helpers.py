"""Shared helpers for --follow streaming across commands."""

import json
from typing import Any

import httpx
import typer

from sculpt.client import Client
from sculpt.commands.data_types import AgentStatusOutput
from sculpt.formatting import cli_error
from sculpt.message_formatting import format_message
from sculpt.session import SessionTokenError
from sculpt.session import get_session_token
from sculpt.ws_client import AgentSnapshot
from sculpt.ws_client import ExitReason
from sculpt.ws_client import follow_agent


def get_session_token_safe(base_url: str, json_output: bool) -> str:
    """Get a session token, exiting on failure."""
    try:
        return get_session_token(Client(base_url=base_url))
    except SessionTokenError as e:
        cli_error(str(e), json_output=json_output)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        cli_error(f"Could not connect to Sculptor server at {base_url}", json_output=json_output)


def handle_exit_reason(reason: ExitReason, json_output: bool) -> None:
    """Map an ExitReason to an exit code. Always raises typer.Exit or calls cli_error."""
    if json_output:
        typer.echo(json.dumps({"type": "exit", "data": {"reason": reason.value}}, default=str))

    if reason == ExitReason.TERMINAL_STATE:
        raise typer.Exit(code=0)
    elif reason == ExitReason.WAITING:
        raise typer.Exit(code=2)
    elif reason == ExitReason.CTRL_C:
        raise typer.Exit(code=0)
    elif reason == ExitReason.RETRY_EXHAUSTED:
        cli_error("Connection lost: reconnection retries exhausted", json_output=json_output)
    else:
        raise typer.Exit(code=0)


def on_status_json(snapshot: AgentSnapshot) -> None:
    """Emit a status NDJSON envelope."""
    output = AgentStatusOutput(
        id=snapshot.task_id,
        status=snapshot.status,
        updated_at=snapshot.updated_at,
        current_activity=snapshot.current_activity,
        last_activity=snapshot.last_activity,
        waiting_detail=snapshot.waiting_detail,
        error_detail=snapshot.error_detail,
        task_completed=snapshot.task_completed,
        task_total=snapshot.task_total,
        current_task_subject=snapshot.current_task_subject,
    )
    typer.echo(json.dumps({"type": "status", "data": output.model_dump()}, default=str))


def on_reconnect_json() -> None:
    """Emit a reconnected NDJSON envelope."""
    typer.echo(json.dumps({"type": "reconnected", "data": {}}, default=str))


def on_reconnect_text() -> None:
    """Print reconnected notice to stderr."""
    typer.echo("Reconnected", err=True)


def on_reconnect_separator() -> None:
    """Print reconnected separator to stdout."""
    typer.echo("--- Reconnected ---")


def on_messages_json(msgs: list[dict[str, Any]]) -> None:
    """Emit message NDJSON envelopes."""
    for msg in msgs:
        typer.echo(json.dumps({"type": "message", "data": msg}, default=str))


def on_messages_text(msgs: list[dict[str, Any]]) -> None:
    """Format and print messages."""
    for msg in msgs:
        typer.echo(format_message(msg))
        typer.echo()


def on_messages_text_with_limit(
    msgs: list[dict[str, Any]], effective_limit: int | None, is_first_batch: list[bool]
) -> None:
    """Format and print messages, applying limit to the first batch only."""
    batch = msgs
    if is_first_batch[0] and effective_limit is not None:
        batch = msgs[-effective_limit:]
    is_first_batch[0] = False
    for msg in batch:
        typer.echo(format_message(msg))
        typer.echo()


def on_messages_json_with_limit(
    msgs: list[dict[str, Any]], effective_limit: int | None, is_first_batch: list[bool]
) -> None:
    """Emit message NDJSON envelopes, applying limit to the first batch only."""
    batch = msgs
    if is_first_batch[0] and effective_limit is not None:
        batch = msgs[-effective_limit:]
    is_first_batch[0] = False
    for msg in batch:
        typer.echo(json.dumps({"type": "message", "data": msg}, default=str))


def noop_status(_snapshot: AgentSnapshot) -> None:
    pass


def noop_messages(_msgs: list[dict[str, Any]]) -> None:
    pass


def on_partial_json(partial: dict[str, Any] | None) -> None:
    """Emit a partial-message NDJSON envelope.

    Fires while a streaming chat message is in flight (with the message-so-far
    payload) and once with `null` data to mark stream end. Use this to render
    streaming text to a `--follow --json` consumer that today only sees
    completed messages.
    """
    typer.echo(json.dumps({"type": "partial", "data": partial}, default=str))


def follow_and_stream_messages(base_url: str, agent_id: str, *, json_output: bool) -> None:
    """Follow an agent and stream its messages. Used by run and send commands."""
    session_token = get_session_token_safe(base_url, json_output)
    if json_output:
        status_cb = on_status_json
        messages_cb = on_messages_json
        reconnect_cb = on_reconnect_json
    else:
        status_cb = noop_status
        messages_cb = on_messages_text
        reconnect_cb = on_reconnect_separator

    exit_reason = follow_agent(
        base_url, session_token, agent_id, status_cb, messages_cb, reconnect_cb
    )
    handle_exit_reason(exit_reason, json_output)
