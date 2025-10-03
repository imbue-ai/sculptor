import datetime
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

import typer
from loguru import logger
from typing_extensions import Annotated
from uvicorn import Config
from uvicorn import Server

from imbue_core.git import get_repo_url_from_folder
from imbue_core.log_utils import ensure_core_log_levels_configured
from imbue_core.s3_uploader import setup_s3_uploads
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry import init_anonymous_posthog
from imbue_core.sculptor.telemetry import init_posthog
from imbue_core.sculptor.telemetry import make_telemetry_event_data
from imbue_core.sculptor.telemetry import mirror_exception_to_posthog
from imbue_core.sculptor.telemetry import without_consent
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.sculptor.telemetry_constants import UserAction
from sculptor import version as sculptor_version
from sculptor.config import user_config
from sculptor.config.telemetry_info import get_onboarding_telemetry_info
from sculptor.config.telemetry_info import get_telemetry_info
from sculptor.database.utils import maybe_get_db_path
from sculptor.services.data_model_service.sql_implementation import register_on_downgrade_detected_should_retry
from sculptor.utils.build import get_build_metadata
from sculptor.utils.errors import setup_sentry
from sculptor.utils.logs import setup_loggers
from sculptor.utils.process_utils import get_original_parent_pid
from sculptor.web.app import APP
from sculptor.web.app import ensure_posthog_user_identified
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import register_on_startup


class UpstreamUrlPayload(PosthogEventPayload):
    upstream_url: str | None = without_consent()


typer_cli = typer.Typer(
    name="sculptor",
    help="Sculptor is a tool to help you build and maintain your codebase.",
    no_args_is_help=False,
    invoke_without_command=True,
)


def get_bool_env_flag(flag_name: str, is_default_true: bool) -> bool:
    if flag_name not in os.environ:
        return is_default_true
    return os.environ[flag_name].lower() in ("1", "t", "true")


class SyncCloseServer(Server):
    async def _wait_tasks_to_complete(self) -> None:
        APP.shutdown_event.set()
        await super()._wait_tasks_to_complete()


def cmd_version(value: bool) -> None:
    """Print the Sculptor version."""
    if value:
        typer.echo(f"Sculptor version: {sculptor_version.__version__}")
        raise typer.Exit()


def _emit_user_config_settings_loaded() -> None:
    """Fires a PostHog event because config settings were loaded."""
    telemetry_info = ensure_posthog_user_identified()
    telemetry_data = make_telemetry_event_data(telemetry_info)
    emit_posthog_event(
        PosthogEventModel(
            name=SculptorPosthogEvent.ONBOARDING_USER_CONFIG_SETTINGS,
            component=ProductComponent.ONBOARDING,
            payload=telemetry_data,
        )
    )
    emit_posthog_event(
        PosthogEventModel(
            name=SculptorPosthogEvent.ONBOARDING_USER_CONFIG_SETTINGS_LOADED,
            component=ProductComponent.ONBOARDING,
            payload=telemetry_data,
        )
    )


def ensure_docker_on_path():
    """Expand the path so we can find docker.

    If we're running this code within a Mac app the path is limited, so calls to
    docker could fail without this.
    """
    extra_path = ["/usr/local/bin", "/opt/homebrew/bin", "/Applications/Docker.app/Contents/Resources/bin"]
    os.environ["PATH"] = os.pathsep.join(extra_path + [os.environ.get("PATH", "")])


def running_under_pyinstaller() -> bool:
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


if running_under_pyinstaller() and platform.system() == "Darwin":
    ensure_docker_on_path()


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
) -> None:
    # Perform any distribution specific setup
    if packaged_entrypoint:
        distribution_specific_setup()

    # Install internal log levels for exception reporting
    ensure_core_log_levels_configured()

    settings = get_settings()

    metadata = get_build_metadata(in_testing=settings.TESTING.INTEGRATION_ENABLED)
    setup_s3_uploads(is_production=metadata.is_production)
    setup_loggers(
        log_file=Path(settings.LOG_PATH) / "server" / "logs.jsonl",
        level=settings.LOG_LEVEL,
    )

    # Only enable sentry during production runs
    if metadata.is_production:
        db_path = maybe_get_db_path(settings.DATABASE_URL)
        assert db_path is not None
        # NOTE: if there's no user config yet, the sentry will be anonymous until the user inputs their email
        setup_sentry(
            metadata, Path(settings.LOG_PATH) / "server", str(db_path), before_send=mirror_exception_to_posthog
        )

    # We either successfully initialize the config from file, or need to perform onboarding.
    user_config_loaded = user_config.initialize_from_file()

    if user_config_loaded:
        logged_in_telemetry_info = get_telemetry_info()
        assert logged_in_telemetry_info, "User is logged in, telemetry must be found"
        init_posthog(logged_in_telemetry_info)
        _emit_user_config_settings_loaded()

        # We only emit this when we've initialized from file because otherwise we're going into onboarding.
        if project:
            _emit_upstream_url_event(project)

    else:
        # We start an anonymized PostHog instance to capture user onboarding. On signup we'll identify the user and
        # allow PostHog to merge their onboarding events with their "signed-in" identity.
        init_anonymous_posthog(get_onboarding_telemetry_info())

    # Fire this for anon and ident users.
    emit_posthog_event(
        PosthogEventModel(name=SculptorPosthogEvent.DESKTOP_BACKEND_STARTED, component=ProductComponent.ONBOARDING)
    )

    if not user_config_loaded:
        # This might be a tad premature to load this event, but we are confident that their Electron browser is going to
        # drop them into the Onboarding flow.
        emit_posthog_event(
            PosthogEventModel(
                name=SculptorPosthogEvent.ONBOARDING_INITIALIZATION, component=ProductComponent.ONBOARDING
            )
        )

    # Using the globally configured user_config
    port = port or get_settings().BACKEND_PORT

    # Print version of Sculptor that is running
    typer.echo("Starting Sculptor server version " + sculptor_version.__version__)

    # Store the initial project path in app state for middleware to pick up
    if project:
        APP.state.initial_project = project

    # We bind to 127.0.0.1 to avoid exposing the server to the network by default.
    # (In theory, we could use "localhost" to also support IPv6 [::1] but we'd need to handle ipv6 in docker port binding setup then.)
    server = SyncCloseServer(config=Config(APP, host="127.0.0.1", port=port, log_config=None, log_level=None))
    frontend_port = int(os.environ.get("SCULPTOR_FRONTEND_PORT", 5174))

    if serve_static:
        port = port
    else:
        port = frontend_port

    if open_browser:
        register_on_startup(lambda: _start_browser(f"http://localhost:{port}"))

    register_on_downgrade_detected_should_retry(_maybe_reset_db_to_resolve_downgrade)
    server.run()


def _maybe_reset_db_to_resolve_downgrade(database_url: str) -> bool:
    database_path = maybe_get_db_path(database_url)
    if database_path is None or not database_path.exists() or not database_path.is_file():
        return False
    backup_path = database_path.with_name(database_path.name + ".backup." + datetime.datetime.now().isoformat())
    typer.echo(
        f"\nIt seems like you are attempting to run an older version of Sculptor which is not compatible with your task database at {database_path}.\n"
    )
    reset_answer = typer.prompt(f"Do you want to reset it? (Your old data will be backed up to {backup_path}.)")
    is_reset_desired = reset_answer.lower() in ("yes", "y", "true")
    if is_reset_desired:
        typer.echo("Backing up the database...")
        shutil.copy(database_path, backup_path)
        typer.echo("Resetting the database...")
        database_path.unlink()
        # In case we are running in WAL mode, just to be sure:
        database_path.with_suffix(".wal").unlink(missing_ok=True)
        database_path.with_suffix(".shm").unlink(missing_ok=True)
    return is_reset_desired


def _emit_upstream_url_event(project_path: Path) -> None:
    try:
        upstream_url = get_repo_url_from_folder(project_path)
    except subprocess.CalledProcessError:
        upstream_url = None

    payload = UpstreamUrlPayload(
        upstream_url=upstream_url,
    )

    event = PosthogEventModel(
        name=SculptorPosthogEvent.STARTUP_REMOTE_URL,
        component=ProductComponent.STARTUP,
        action=UserAction.CALLED,
        payload=payload,
    )
    emit_posthog_event(event)


def _start_browser(target_url: str) -> None:
    logger.info("Done starting server! Please open {} in your browser.", target_url)
    webbrowser.open(target_url, new=2)


def entrypoint() -> None:
    """Entrypoint for Sculptor when run from a distribution.

    This makes sure to run any distribution-specific setup prior to running the cli.
    """
    distribution_specific_setup()
    typer_cli()


def distribution_specific_setup():
    """Any specific setup or environment variables we wish to set that ONLY
    affect the distributed versions of the Python backend.
    """
    # Ensure the distributed version of our code uses production PostHog
    os.environ["USE_PROD_POSTHOG"] = "1"


if __name__ == "__main__":
    # we call this first to make sure it is cached as early as possible
    get_original_parent_pid()
    # the actually run the program
    typer_cli()
