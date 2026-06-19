import inspect
import signal
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import asynccontextmanager
from functools import wraps
from threading import Event
from threading import Thread
from typing import Any
from typing import Callable

from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from loguru import logger
from pydantic import alias_generators
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from sculptor.config.settings import SculptorSettings
from sculptor.foundation.common import is_live_debugging
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.itertools import only
from sculptor.foundation.subprocess_utils import terminate_isolated_process_groups
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.service_collections.service_collection import get_services
from sculptor.services.project_service.default_implementation import update_most_recently_used_project
from sculptor.services.workspace_service.legacy_cleanup import cleanup_obsolete_mru_files
from sculptor.utils.migration import ensure_sculptor_folder_ready
from sculptor.utils.shutdown import GLOBAL_SHUTDOWN_EVENT
from sculptor.utils.tracing import get_trace_to_path
from sculptor.utils.tracing import is_tracing_enabled
from sculptor.utils.tracing import stop_and_write_trace
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.streams import Scope
from sculptor.web.streams import ServerStopped
from sculptor.web.streams import resolve_scope


def mount_static_files(app: FastAPI, static_directory: str) -> None:
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend-dist")


# Note that this is overridden in tests to use the test settings
def get_settings() -> SculptorSettings:
    return SculptorSettings()


_DEFAULT_EVENT = Event()


def shutdown_event() -> Event:
    return _DEFAULT_EVENT


# This is the dependency that actually creates the service collection when the application starts up.
# (The service collection is then stored in the app state for later use.)
def services_factory(
    root_concurrency_group: ConcurrencyGroup, settings: SculptorSettings = Depends(get_settings)
) -> CompleteServiceCollection:
    return get_services(root_concurrency_group, settings)


# This is a convenience function to get the already created services from the app state.
def get_services_from_request_or_websocket(request_or_websocket: Request | WebSocket) -> CompleteServiceCollection:
    return request_or_websocket.app.state.services


def get_root_concurrency_group(request_or_websocket: Request | WebSocket) -> ConcurrencyGroup:
    return request_or_websocket.app.state.root_concurrency_group


def get_user_session(
    request: Request,
) -> UserSession:
    services = get_services_from_request_or_websocket(request)
    return _get_user_session(request=request, services=services)


def get_user_session_for_websocket(
    websocket: WebSocket,
) -> UserSession:
    services = get_services_from_request_or_websocket(websocket)
    return _get_user_session(request=websocket, services=services)


def resolve_stream_scope(websocket: WebSocket) -> Scope:
    """FastAPI Depends-able wrapper around `streams.resolve_scope`.

    Lives here (not in `streams.py`) because `streams` cannot import the
    middleware functions it needs — `middleware` already imports
    `ServerStopped` from `streams`, and a top-level import the other way
    would be a cycle. Keeping the WS-extraction shim alongside the other
    request-bound helpers avoids that cycle without function-local imports.
    """
    user_session = get_user_session_for_websocket(websocket)
    services = get_services_from_request_or_websocket(websocket)
    return resolve_scope(
        scope_values=websocket.query_params.getlist("scope"),
        user_session=user_session,
        services=services,
    )


def _get_user_session(
    request: Request | WebSocket,
    services: CompleteServiceCollection,
) -> UserSession:
    header_request_id = request.headers.get("Sculptor-Request-ID", None)
    if header_request_id is None:
        request_id = RequestID()
    else:
        request_id = RequestID(header_request_id)

    # CSRF-like vulnerabilities are mitigated using the SessionTokenMiddleware.
    user_session = authenticate_anonymous(services, request_id)

    user_session.logger_kwargs.update(
        dict(
            request_id=str(user_session.request_id),
            user_reference=str(user_session.user_reference),
            route=request.url.path,
        )
    )
    return user_session


class DecoratedAPIRouter(APIRouter):
    def __init__(self, *args: Any, decorator: Callable[..., Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.decorator = decorator

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs):
        if "operation_id" not in kwargs or kwargs["operation_id"] is None:
            kwargs["operation_id"] = alias_generators.to_camel(endpoint.__name__)

        if self.decorator:
            endpoint = self.decorator(endpoint)
        return super().add_api_route(path, endpoint, **kwargs)


def add_logging_context(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Get the user_session from the function's kwargs or bound arguments
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        user_session: UserSession | None = bound.arguments.get("user_session")

        if user_session is None:
            # If not in kwargs, try to find it positionally
            for param_name, param in sig.parameters.items():
                if param.annotation.__name__ == "UserSession" or param_name == "user_session":
                    user_session = bound.arguments.get(param_name)
                    break

        if user_session is None:
            # Some endpoints allow anonymous access and that's fine.
            return run_sync_function_with_debugging_support_if_enabled(func, args, kwargs)

        with logger.contextualize(**user_session.logger_kwargs):
            return run_sync_function_with_debugging_support_if_enabled(func, args, kwargs)

    return sync_wrapper


def run_sync_function_with_debugging_support_if_enabled(
    func: Callable[..., Any], args: Sequence[Any], kwargs: Mapping[str, Any]
) -> Any:
    """
    If we are not debugging, then we run the function directly and return the result.

    If we are debugging, then we run the function in a thread.
    This allows the debugger to catch unhandled exceptions.
    Without this, fastapi and uvicorn end up returning a 500 instead of raising,
    so the auto-attach behavior doesn't work.

    This function *should* be called in each place that we call a sync function.
    """
    if is_live_debugging():
        output_container = []
        thread = Thread(
            target=_run_in_thread_so_that_unhandled_exceptions_can_be_caught_by_a_debugger,
            args=(func, args, kwargs, output_container),
        )
        thread.start()
        thread.join()
        result = only(output_container)
        if isinstance(result, BaseException):
            raise result
        return result
    # in the normal case, we're already in a thread in an async context anyway, so just call the function
    else:
        return func(*args, **kwargs)


# simply part of the implementation of `run_sync_function_with_debugging_support_if_enabled`, see docstring there
def _run_in_thread_so_that_unhandled_exceptions_can_be_caught_by_a_debugger(
    func: Callable[..., Any],
    args: Sequence[Any],
    kwargs: Mapping[str, Any],
    output_container: list[Any],
) -> None:
    try:
        result = func(*args, **kwargs)
    except (HTTPException, ServerStopped) as e:
        output_container.append(e)
    except BaseException as e:
        output_container.append(e)
        # these we re-raise, since we want the debugger to catch them
        raise
    else:
        output_container.append(result)


on_startup_callback: Callable[[], None] = lambda: None  # noqa: E731


def register_on_startup(callback: Callable[[], None]) -> None:
    global on_startup_callback
    on_startup_callback = callback


def _write_trace_if_enabled() -> None:
    """Flush the perfetto/viztracer trace file. Called from the lifespan's
    ``finally`` block so it runs whether shutdown was clean or signal-induced.

    Lives here (rather than in a ``try/finally`` around ``server.run()`` in
    ``cli/app.py``) because uvicorn's ``Server.capture_signals`` restores the
    default signal handlers in its own ``finally`` and then re-raises the
    captured signal via ``signal.raise_signal``. By the time any ``finally``
    outside the FastAPI lifespan would run, the process has been killed by
    the default SIGTERM/SIGINT handler. The lifespan's own teardown runs
    *during* uvicorn's normal shutdown sequence, before that re-raise, so
    SIGTERM/Ctrl-C — the realistic way to stop a dev-mode Sculptor — still
    produces a usable trace artifact.
    """
    if not is_tracing_enabled():
        return
    try:
        stop_and_write_trace()
        logger.info(
            "Trace written to {}. Open https://ui.perfetto.dev and drop this file there to view.",
            get_trace_to_path(),
        )
    except Exception as e:
        logger.opt(exception=e).error("Failed to write trace file")


class App(FastAPI):
    shutdown_event: Event


@asynccontextmanager
async def lifespan(app: App):
    """
    Initializes the application. (It has to be async.)
    """
    ensure_sculptor_folder_ready()
    cleanup_obsolete_mru_files()

    if get_settings in app.dependency_overrides:
        settings = app.dependency_overrides[get_settings]()
    else:
        settings = get_settings()

    try:
        with ConcurrencyGroup(name="lifespan") as root_concurrency_group:
            if services_factory in app.dependency_overrides:
                services = app.dependency_overrides[services_factory](root_concurrency_group, settings)
            else:
                services = services_factory(root_concurrency_group, settings)
            with services.run_all():
                app.state.services = services
                app.state.root_concurrency_group = root_concurrency_group
                if shutdown_event in app.dependency_overrides:
                    event = app.dependency_overrides[shutdown_event]()
                else:
                    event = shutdown_event()
                app.shutdown_event = event
                # activate all known projects
                with services.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                    for project in transaction.get_projects():
                        services.project_service.activate_project(project)

                # Reconcile workspace setup state — `running` rows from a prior
                # crash are converted to `failed`; `pending` rows whose project
                # no longer has a setup command (or the toggle is off) become
                # `not_configured`.
                try:
                    # pyrefly: ignore [missing-attribute]
                    services.workspace_service.reconcile_setup_state()
                except Exception as exc:
                    logger.opt(exception=exc).error("Failed to reconcile workspace setup state on startup")

                # Set initial project if provided via CLI by setting it as the most recently used project.
                initial_project_path = getattr(app.state, "initial_project", None)
                if initial_project_path:
                    logger.info("Setting initial project from CLI: {}", initial_project_path)

                    with services.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                        project = services.project_service.initialize_project(
                            project_path=initial_project_path,
                            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
                            transaction=transaction,
                        )
                        services.project_service.activate_project(project)
                        update_most_recently_used_project(project_id=project.object_id)

                if settings.SERVE_STATIC_FILES_DIR is not None:
                    mount_static_files(app, settings.SERVE_STATIC_FILES_DIR)

                logger.info("Using DB: {}", services.settings.DATABASE_URL)

                logger.info("Server is ready to accept requests!")
                on_startup_callback()
                yield
                # SCU-925/SCU-211: before flipping the global shutdown flag,
                # broadcast SIGTERM to every isolated agent process group
                # (registered by ``run_local_command_modern_version`` when
                # ``isolate_process_group=True``). The agent CLI is no longer
                # in Sculptor's process group (SCU-211), so the test harness's
                # ``killpg(Sculptor pgroup, SIGTERM)`` never reaches it on
                # restart — without this forward, the agent is orphaned,
                # exits 1 on stdin EOF (rather than 143 via its SIGTERM
                # handler), and surfaces as a red "Agent died with exit
                # code 1" ErrorBlock after restart (the SCU-925 regression).
                #
                # Setting the concurrency group's shutdown_event globally is
                # too broad — it makes the v1 agent loop short-circuit via
                # ``AgentPaused`` before the wrapper can emit
                # ``RequestStoppedAgentMessage``, which the replay-on-restart
                # regression tests rely on to advance the dedup cursor.
                terminate_isolated_process_groups(signal.SIGTERM)
                # Set the global IS_SHUTTING_DOWN flag as the first thing so that all the threads immediately know we are shutting down.
                # (Even before the context managers exit handlers are called.)
                GLOBAL_SHUTDOWN_EVENT.set()
    finally:
        GLOBAL_SHUTDOWN_EVENT.set()
        _write_trace_if_enabled()
