"""Low-level diagnostics against a running Sculptor backend.

**For Sculptor development only — not end-user functionality.** These commands
exist to debug and profile the Sculptor backend itself; they are not part of
the product surface and may change or disappear without notice.

    sculpt debug threads              # print a Python traceback for every thread
    sculpt debug trace start|stop|status   # profile the backend (viztracer)

``threads`` is the lightweight alternative to a full trace when the backend
looks wedged: it returns an instant snapshot of every thread's Python stack via
``sys._current_frames()`` (greenlet-safe — no signals, no C-stack walk). All
commands require the session token, which ``get_authenticated_client`` resolves.
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
