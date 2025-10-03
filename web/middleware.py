import inspect
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
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from loguru import logger
from pydantic import alias_generators
from starlette import status
from starlette.requests import HTTPConnection
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import is_live_debugging
from imbue_core.itertools import only
from imbue_core.s3_uploader import wait_for_s3_uploads
from sculptor.config.settings import SculptorSettings
from sculptor.config.user_config import get_user_config_instance
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.service_collections.service_collection import get_services_cached
from sculptor.services.project_service.default_implementation import get_most_recently_used_project_id
from sculptor.utils.errors import set_sentry_user_for_current_scope
from sculptor.web.auth import InvalidTokenError
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.streams import ServerStopped

# Don't use auto_error since fastAPI seems to think 403 is the appropriate response in case of missing auth but it's actually 401.
SECURITY = HTTPBearer(auto_error=False)


def mount_static_files(app: FastAPI, static_directory: str) -> None:
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend-dist")


# TODO: we can probably @cache this rather than rebuild every request
# Note that this is overridden in tests to use the test settings
def get_settings() -> SculptorSettings:
    return SculptorSettings()


_DEFAULT_EVENT = Event()


def shutdown_event() -> Event:
    return _DEFAULT_EVENT


def services_factory(settings: SculptorSettings = Depends(get_settings)) -> CompleteServiceCollection:
    return get_services_cached(settings)


def get_user_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(SECURITY),
    services: CompleteServiceCollection = Depends(services_factory),
    settings: SculptorSettings = Depends(get_settings),
) -> UserSession:
    return _get_user_session(
        request=request,
        credentials=credentials,
        services=services,
        settings=settings,
    )


def get_user_session_for_websocket(
    websocket: WebSocket,
    services: CompleteServiceCollection = Depends(services_factory),
    settings: SculptorSettings = Depends(get_settings),
) -> UserSession:
    return _get_user_session(
        request=websocket,
        credentials=None,
        services=services,
        settings=settings,
    )


def _get_user_session(
    request: HTTPConnection,
    credentials: HTTPAuthorizationCredentials | None,
    services: CompleteServiceCollection,
    settings: SculptorSettings,
) -> UserSession:
    header_request_id = request.headers.get("X-Request-ID", None)
    if header_request_id is None:
        request_id = RequestID()
    else:
        request_id = RequestID(header_request_id)
    access_token: str | None = None
    if credentials is not None:
        access_token = credentials.credentials
    elif "jwt" in request.query_params:
        # Support JWT in query parameters for EventSource connections which cannot supply headers.
        access_token = request.query_params["jwt"]

    if access_token is None and not settings.ALLOW_ANONYMOUS_USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if access_token is not None:
        try:
            user_session = authenticate(json_web_token=access_token, services=services, request_id=request_id)
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # CSRF-like vulnerabilities are mitigated using the AppSecretMiddleware.
        user_session = authenticate_anonymous(services, request_id)
    # FIXME: after we move to actually being logged in, we should get the user email from the session maybe?
    #       set_sentry_user_for_current_scope(user_session.user_email)
    #  for now we get it from the current config if that exists:
    current_config = get_user_config_instance()
    user_email = user_session.user_email
    if current_config is not None and current_config.user_email:
        user_email = current_config.user_email
    set_sentry_user_for_current_scope(user_email)
    user_session.logger_kwargs.update(
        dict(
            request_id=str(user_session.request_id),
            user_reference=str(user_session.user_reference),
            route=request.url.path,
        )
    )
    return user_session


class DecoratedAPIRouter(APIRouter):
    def __init__(self, *args, decorator=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.decorator = decorator

    # pyre-ignore[14]: we're using kwargs instead of spelling out every keyword argument here, but Pyre mistakenly thinks it's not consistent with the overridden method
    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs):
        if "operation_id" not in kwargs or kwargs["operation_id"] is None:
            kwargs["operation_id"] = alias_generators.to_camel(endpoint.__name__)

        if self.decorator:
            endpoint = self.decorator(endpoint)
        return super().add_api_route(path, endpoint, **kwargs)


def add_logging_context(func):
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
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


def run_sync_function_with_debugging_support_if_enabled(func, args, kwargs):
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
    func, args, kwargs, output_container
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


on_startup_callback = lambda: None


def register_on_startup(callback: Callable) -> None:
    global on_startup_callback
    on_startup_callback = callback


class App(FastAPI):
    # pyre-ignore[13]: Pyre doesn't like uninitialized fields; we are in fact initializing this field, just in a hacky outside the __init__ method.
    shutdown_event: Event


@asynccontextmanager
async def lifespan(app: App):
    """
    Formerly `@app.on_event("startup")`, this is used to initialize the application.
    (It has to be async.)

    """
    if get_settings in app.dependency_overrides:
        settings = app.dependency_overrides[get_settings]()
    else:
        settings = get_settings()

    if services_factory in app.dependency_overrides:
        services = app.dependency_overrides[services_factory](settings)
    else:
        services = services_factory(settings)
    if shutdown_event in app.dependency_overrides:
        event = app.dependency_overrides[shutdown_event]()
    else:
        event = shutdown_event()
    app.shutdown_event = event
    try:
        services.start_all()

        # activate all known projects
        with services.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            for project in transaction.get_projects():
                services.project_service.activate_project(project)

        # Set initial project if provided via CLI by re-activating it
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
        # otherwise re-activate most recently used project, if any
        else:
            most_recent_project_id = get_most_recently_used_project_id()
            if most_recent_project_id is not None:
                with services.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                    project = transaction.get_project(project_id=most_recent_project_id)
                    if project is not None:
                        services.project_service.activate_project(project)

        if settings.SERVE_STATIC_FILES_DIR is not None:
            mount_static_files(app, settings.SERVE_STATIC_FILES_DIR)

        logger.info("Using DB: {}", services.settings.DATABASE_URL)

        logger.info("Server is ready to accept requests!")
        on_startup_callback()
    except Exception as e:
        log_exception(e, "Error in lifespan startup")
        raise
    else:
        yield
    finally:
        try:
            services.stop_all()
        except Exception as e:
            log_exception(e, "Error in stopping services")
            raise
        finally:
            try:
                user_config = get_user_config_instance()
                if user_config and user_config.is_error_reporting_enabled:
                    wait_for_s3_uploads(5.0)
            except Exception as e:
                log_exception(e, "Error in waiting for S3 uploads")
                raise
