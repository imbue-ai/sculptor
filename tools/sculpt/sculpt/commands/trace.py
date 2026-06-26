"""Arm/disarm the backend's viztracer profiler at runtime.

**For Sculptor development only — not end-user functionality.** Registered as a
subgroup of ``sculpt debug`` (see ``debug.py``). Thin wrappers over the
trace-control HTTP endpoints so a developer can profile a running (including a
signed, production) backend without restarting it or passing ``--trace-to`` at
launch:

    sculpt debug trace start         # arm
    ...reproduce the slow thing...
    sculpt debug trace stop          # flush the Chrome-JSON file, print its path

Drop the resulting file into https://ui.perfetto.dev to inspect it. Unlike the
``/api/v1/trace/batch`` ingest endpoint, these require the session token, which
``get_authenticated_client`` resolves automatically.
"""

import json

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

trace_app = typer.Typer(help="Profile a running Sculptor backend with viztracer (Sculptor development only).")

_JSON_OPTION = typer.Option(False, "--json", help="Output as JSON")


def _request(method: str, path: str, json_output: bool, body: dict | None = None) -> dict:
    """Make an authenticated request to a trace-control endpoint and return the
    decoded JSON body. Exits (code 1) with a friendly message on connection
    failure or a non-2xx response.

    A 409 from these endpoints is a trace-state conflict (already-running /
    not-running) whose ``detail`` is already a complete, user-facing sentence —
    including the active trace's path — so it's surfaced as-is rather than under
    the generic 'Request failed with status N' framing."""
    client = get_authenticated_client(get_default_base_url())
    try:
        response = client.get_httpx_client().request(method, path, json=body)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "")
        except (json.JSONDecodeError, ValueError):
            detail = response.text
        if response.status_code == 409 and detail:
            cli_error(detail, json_output=json_output)
        cli_error(f"Request failed with status {response.status_code}", detail=detail, json_output=json_output)
    return response.json()


@trace_app.command("start")
def start(
    tracer_entries: int | None = typer.Option(
        None,
        "--tracer-entries",
        help="Ring-buffer size (entries). Larger = longer capture window, more memory. Defaults to the backend's ad-hoc default.",
    ),
    json_output: bool = _JSON_OPTION,
) -> None:
    """Arm viztracer on the running backend."""
    body = {"tracer_entries": tracer_entries} if tracer_entries is not None else {}
    result = _request("POST", "/api/v1/trace/start", json_output, body=body)
    if json_output:
        typer.echo(json.dumps(result))
        return
    # The backend serializes responses with camelCase aliases (SerializableModel).
    typer.echo(f"Tracing armed. Output will be written to:\n  {result['outputPath']}")
    typer.echo("Reproduce the slow path, then run `sculpt debug trace stop`.")


@trace_app.command("stop")
def stop(json_output: bool = _JSON_OPTION) -> None:
    """Stop tracing and flush the combined trace file to disk."""
    result = _request("POST", "/api/v1/trace/stop", json_output)
    if json_output:
        typer.echo(json.dumps(result))
        return
    typer.echo(f"Trace written to:\n  {result['outputPath']}")
    typer.echo(f"  {result['backendEventCount']} backend events, {result['externalEventCount']} external events.")
    typer.echo("Open https://ui.perfetto.dev and drop the file there to view.")


@trace_app.command("status")
def status(json_output: bool = _JSON_OPTION) -> None:
    """Report whether a trace is currently running."""
    result = _request("GET", "/api/v1/trace/status", json_output)
    if json_output:
        typer.echo(json.dumps(result))
        return
    if result["enabled"]:
        typer.echo(f"Tracing is RUNNING. Output -> {result['outputPath']}")
        typer.echo(f"  {result['bufferedExternalEvents']} external events buffered.")
    else:
        typer.echo("Tracing is not running.")
