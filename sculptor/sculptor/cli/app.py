"""Sculptor backend CLI + server startup.

Imported by ``sculptor.cli.main`` only after the early helper-mode
dispatch has decided this process is NOT a pty helper.  Running this
module directly as ``python -m sculptor.cli.app`` would execute the
heavy top-level imports below (typer, loguru, uvicorn,
``sculptor.web.app``, ...) -- exactly what the pre-import
bootstrap in ``cli/main.py`` exists to defer until we know we are
actually starting the backend.
"""

import os
import webbrowser
from pathlib import Path

import typer
from loguru import logger
from typing_extensions import Annotated
from uvicorn import Config
from uvicorn import Server

from sculptor import version as sculptor_version
from sculptor.foundation.log_utils import ensure_core_log_levels_configured
from sculptor.services.user_config.user_config import initialize_from_file
from sculptor.utils.errors import setup_irrecoverable_exception_handler
from sculptor.utils.logs import setup_loggers
from sculptor.utils.tracing import get_trace_to_path
from sculptor.utils.tracing import is_tracing_enabled
from sculptor.web.app import APP
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import register_on_startup

# Single-line so the implicit_string_concat ratchet is happy and so the
# typer.BadParameter output does not carry the indentation a triple-quoted
# block would introduce.
_LATE_START_ERROR_MESSAGE = "--trace-to must be passed at the sculptor CLI entry point so the bootstrap in cli/main.py can start viztracer before the backend imports run. Passing it through the typer callback alone is not supported."

# Fallback frontend (vite) port used only when SCULPTOR_FRONTEND_PORT is unset;
# in dev mode the launcher normally sets that variable explicitly.
_DEFAULT_FRONTEND_PORT = 5174


typer_cli = typer.Typer(
    name="sculptor",
    help="Sculptor is a tool to help you build and maintain your codebase.",
    no_args_is_help=False,
    invoke_without_command=True,
)


class SyncCloseServer(Server):
    async def _wait_tasks_to_complete(self) -> None:
        APP.shutdown_event.set()
        await super()._wait_tasks_to_complete()


def cmd_version(value: bool) -> None:
    """Print the Sculptor version."""
    if value:
        typer.echo(f"Sculptor version: {sculptor_version.__version__}")
        raise typer.Exit()


@typer_cli.callback()
def main(
    project: Path | None = typer.Argument(
        None,
        exists=False,
        help="Path to the project repository. If not provided, current directory is used.",
        resolve_path=True,
    ),
    version: Annotated[bool | None, typer.Option("--version", callback=cmd_version)] = None,
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-open-browser",
        help="If the browser should automatically open on sculptor startup.",
    ),
    serve_static: bool = typer.Option(
        True,
        "--serve-static/--no-serve-static",
        help="If true, the main webserver will also serve the distributed asset files.",
        hidden=True,
    ),
    packaged_entrypoint: bool = typer.Option(
        False,
        "--packaged-entrypoint",
        help="Iff true this indicates we're running a production build, and the appropriate values will be set. This is identical behaviour to running entrypoint(), but intended for cases where that function cannot be accessed",
        hidden=True,
    ),
    port: int | None = typer.Option(
        None,
        "--port",
        help="Use to override the port",
    ),
    trace_to: Path | None = typer.Option(
        None,
        "--trace-to",
        help="If set, write a combined Chrome JSON trace file (backend + frontend + Electron-main) to this path on exit. Captures approximately 80 seconds of activity per session. Open the result at https://ui.perfetto.dev.",
    ),
) -> None:
    # Perform any distribution specific setup
    if packaged_entrypoint:
        distribution_specific_setup()

    # Install internal log levels for exception reporting
    ensure_core_log_levels_configured()

    settings = get_settings()

    setup_loggers(
        log_file=Path(settings.LOG_PATH) / "server" / "logs.jsonl",
        level=settings.LOG_LEVEL,
    )

    # Make all ObservableThreads crash the process immediately on irrecoverable exceptions.
    setup_irrecoverable_exception_handler()

    # We either successfully initialize the config from file, or need to perform onboarding.
    initialize_from_file()

    # Using the globally configured user_config
    port = port or get_settings().BACKEND_PORT
    # Publish the resolved port so downstream code (e.g. agent environment
    # setup) sees the actual port the server is listening on, not the default.
    os.environ["SCULPTOR_API_PORT"] = str(port)

    # Print version of Sculptor that is running
    typer.echo("Starting Sculptor server version " + sculptor_version.__version__)

    if is_tracing_enabled():
        logger.info("Tracing enabled, output -> {}", get_trace_to_path())
    elif trace_to is not None:
        # Tracing must be started by the early bootstrap in cli/main.py
        # BEFORE the heavy cli/app import. Reaching here means the bootstrap
        # was bypassed (e.g. a test instantiating the typer app directly).
        # Starting viztracer this late would also leave the renderer's
        # window.__SCULPTOR_TRACING__ mis-inlined for any HTML already
        # served, so the renderer would silently not collect.
        raise typer.BadParameter(_LATE_START_ERROR_MESSAGE, param_hint="--trace-to")

    # Store the initial project path in app state for middleware to pick up
    if project:
        APP.state.initial_project = project

    # We bind to 127.0.0.1 to avoid exposing the server to the network by default.
    # (In theory, we could use "localhost" to also support IPv6 [::1] but we'd need to handle ipv6 in docker port binding setup then.)
    server = SyncCloseServer(config=Config(APP, host=settings.BIND_HOST, port=port, log_config=None, log_level=None))
    frontend_port = int(os.environ.get("SCULPTOR_FRONTEND_PORT", _DEFAULT_FRONTEND_PORT))

    if not serve_static:
        port = frontend_port

    if open_browser:
        register_on_startup(lambda: _start_browser(f"http://localhost:{port}"))

    # The trace flush lives in the FastAPI lifespan's `finally` (see
    # `_write_trace_if_enabled` in `web/middleware.py`), not here. uvicorn's
    # `Server.capture_signals` re-raises captured signals with the default
    # handler reinstalled, so any `finally` around `server.run()` is skipped
    # on SIGTERM/SIGINT — which is the only realistic way to stop a
    # dev-mode Sculptor.
    server.run()


def _start_browser(target_url: str) -> None:
    logger.info("Done starting server! Please open {} in your browser.", target_url)
    webbrowser.open(target_url, new=2)


def entrypoint() -> None:
    """Entrypoint for Sculptor when run from a distribution.

    This makes sure to run any distribution-specific setup prior to running the cli.
    """
    distribution_specific_setup()
    typer_cli()


def distribution_specific_setup() -> None:
    """Any specific setup or environment variables we wish to set that ONLY
    affect the distributed versions of the Python backend.

    Currently a no-op: it remains the extension point (invoked by ``entrypoint``
    and the ``--packaged-entrypoint`` path) for distribution-only configuration.
    """
