"""Low-level diagnostics against a running Sculptor backend.

**For Sculptor development only — not end-user functionality.** These commands
exist to debug and profile the Sculptor backend itself; they are not part of
the product surface and may change or disappear without notice.

    sculpt debug threads              # print a Python traceback for every thread
    sculpt debug heap                 # census the heap to diagnose RSS growth
    sculpt debug trace start|stop|status   # profile the backend (viztracer)

``threads`` is the lightweight alternative to a full trace when the backend
looks wedged: it returns an instant snapshot of every thread's Python stack via
``sys._current_frames()`` (greenlet-safe — no signals, no C-stack walk).
``heap`` censuses live objects (and, with ``--collect``, forces a GC to tell
accumulating garbage apart from live retention). All commands require the
session token, which ``get_authenticated_client`` resolves.
"""

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.commands.trace import trace_app
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

debug_app = typer.Typer(
    help="Diagnostics for a running Sculptor backend. For Sculptor development only — not end-user functionality."
)
debug_app.add_typer(trace_app, name="trace")

_OUTPUT_OPTION = typer.Option(None, "--output", "-o", help="Write the dump to this file instead of stdout.")


@debug_app.command("threads")
def threads(output: str | None = _OUTPUT_OPTION) -> None:
    """Dump a Python traceback for every live backend thread."""
    client = get_authenticated_client(get_default_base_url())
    try:
        response = client.get_httpx_client().get("/api/v1/debug/threads")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error()
    if response.status_code >= 400:
        cli_error(f"Request failed with status {response.status_code}", detail=response.text)
    if output is not None:
        with open(output, "w") as f:
            f.write(response.text)
        typer.echo(f"Thread dump written to {output}")
    else:
        typer.echo(response.text)


@debug_app.command("heap")
def heap(
    collect: bool = typer.Option(
        False,
        "--collect",
        help="Force gc.collect() and report RSS before/after — distinguishes accumulating garbage from live retention.",
    ),
    start_trace: bool = typer.Option(
        False,
        "--start-trace",
        help="Start tracemalloc in the backend (captures allocation sites from now on). Reproduce growth, then re-run plain.",
    ),
    stop_trace: bool = typer.Option(False, "--stop-trace", help="Stop tracemalloc in the backend."),
    trace_frames: int = typer.Option(10, "--trace-frames", help="Frames per allocation captured when starting tracemalloc."),
    top: int = typer.Option(30, "--top", help="How many types / allocation sites to show."),
    limit: int = typer.Option(
        5_000_000,
        "--limit",
        help="Cap objects sized (0 = full census; larger = longer GIL pause on the backend).",
    ),
    output: str | None = _OUTPUT_OPTION,
) -> None:
    """Census the backend heap to diagnose RSS growth (Sculptor development only).

    The census briefly pauses the backend (it walks every tracked object), so it
    can take several seconds on a multi-GB heap; the request timeout is raised
    accordingly. For allocation-site attribution, run once with --start-trace,
    reproduce the growth, then run plain to see the top sites."""
    client = get_authenticated_client(get_default_base_url())
    params: dict[str, object] = {"collect": str(collect).lower(), "top": top, "limit": limit}
    if start_trace:
        params["start_trace"] = trace_frames
    if stop_trace:
        params["stop_trace"] = "true"
    try:
        response = client.get_httpx_client().get("/api/v1/debug/heap", params=params, timeout=300.0)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error()
    if response.status_code >= 400:
        cli_error(f"Request failed with status {response.status_code}", detail=response.text)
    if output is not None:
        with open(output, "w") as f:
            f.write(response.text)
        typer.echo(f"Heap report written to {output}")
    else:
        typer.echo(response.text)
