"""Routes for a repository's jj configuration: colocation, its pre-flight, the jj flag and the bookmarks.

The repository's jj state itself reaches the frontend on the stream, under
`project_jj_state_by_project_id`. One route here is not jj's own: each
workspace kind's default setup command, which differs for jj and which the
repository settings show. app.py includes the router.
"""

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from sculptor.database.models import Project
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import ProjectID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.project_jj_state_service.project_jj_state_service import ColocationAlreadyRunningError
from sculptor.services.project_jj_state_service.project_jj_state_service import ColocationBlockedError
from sculptor.services.project_jj_state_service.project_jj_state_service import JjUnavailableForRepositoryError
from sculptor.services.project_jj_state_service.project_jj_state_service import RepositoryNotColocatedError
from sculptor.services.workspace_service.vcs.checkout_layout import is_isolated_checkout
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.web.auth import UserSession
from sculptor.web.data_types import JjBookmarkChoicesResponse
from sculptor.web.data_types import JjColocationPreflight
from sculptor.web.data_types import UseJjForNewWorkspacesRequest
from sculptor.web.data_types import WorkspaceSetupCommandDefaults
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_services_from_request_or_websocket
from sculptor.web.middleware import get_user_session
from sculptor.web.path_id_validation import validate_project_id

project_jj_router = DecoratedAPIRouter(decorator=add_logging_context)


@project_jj_router.get("/api/v1/projects/{project_id}/jj")
def get_project_jj_preflight(
    project_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> JjColocationPreflight:
    """What colocating the repository with jj would run into; reading it changes nothing in the repository.

    The repository's state on the stream is derived from disk again too.
    """
    services = get_services_from_request_or_websocket(request)
    project = _get_project(services, user_session, validate_project_id(project_id))
    try:
        return services.project_jj_state_service.read_preflight(project)
    except VcsCommandError as e:
        raise HTTPException(status_code=409, detail=f"Cannot read the repository: {e}") from e


@project_jj_router.post("/api/v1/projects/{project_id}/jj/colocate", status_code=202)
def colocate_project_with_jj(
    project_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Start making the repository a jj colocation; its progress and outcome arrive on the stream.

    On success `use_jj_for_new_workspaces` is turned on. Answers 412 when jj is
    unavailable, and 409 when the pre-flight finds a blocker or a colocation
    is already running.
    """
    services = get_services_from_request_or_websocket(request)
    project = _get_project(services, user_session, validate_project_id(project_id))
    try:
        services.project_jj_state_service.start_colocation(project)
    except JjUnavailableForRepositoryError as e:
        raise HTTPException(status_code=412, detail=str(e)) from e
    except (ColocationBlockedError, ColocationAlreadyRunningError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except VcsCommandError as e:
        raise HTTPException(status_code=409, detail=f"Cannot read the repository: {e}") from e


@project_jj_router.put("/api/v1/projects/{project_id}/use_jj_for_new_workspaces")
def update_use_jj_for_new_workspaces(
    project_id: str,
    request: Request,
    use_jj_request: UseJjForNewWorkspacesRequest,
    user_session: UserSession = Depends(get_user_session),
) -> bool:
    """Turn jj workspaces on or off for the repository's new workspaces; existing workspaces keep their kind.

    Turning it on answers 412 when jj is unavailable and 409 when the repository is not colocated.
    """
    validated_project_id = validate_project_id(project_id)
    services = get_services_from_request_or_websocket(request)
    project = _get_project(services, user_session, validated_project_id)
    if use_jj_request.use_jj_for_new_workspaces:
        _require_colocation(services, project)
    with user_session.open_transaction(services) as transaction:
        updated_project = transaction.update_project_fields(
            validated_project_id, use_jj_for_new_workspaces=use_jj_request.use_jj_for_new_workspaces
        )
        if updated_project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    services.project_service.activate_project(updated_project)
    return updated_project.use_jj_for_new_workspaces


@project_jj_router.get("/api/v1/projects/{project_id}/jj/bookmarks")
def list_project_jj_bookmarks(
    project_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> JjBookmarkChoicesResponse:
    """The bookmarks a new jj workspace can start from or target: local and remote, without conflicted ones.

    Answers 412 when jj is unavailable and 409 when the repository is not colocated.
    """
    services = get_services_from_request_or_websocket(request)
    project = _get_project(services, user_session, validate_project_id(project_id))
    try:
        bookmarks = services.project_jj_state_service.list_bookmark_choices(project)
    except JjUnavailableForRepositoryError as e:
        raise HTTPException(status_code=412, detail=str(e)) from e
    except RepositoryNotColocatedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return JjBookmarkChoicesResponse(bookmarks=bookmarks)


@project_jj_router.get("/api/v1/workspace_setup_command_defaults")
def get_workspace_setup_command_defaults(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceSetupCommandDefaults:
    """The setup command each workspace kind runs when its project configures none, from that kind's VCS."""
    workspace_service = get_services_from_request_or_websocket(request).workspace_service
    return WorkspaceSetupCommandDefaults(
        default_setup_command_by_initialization_strategy={
            initialization_strategy: workspace_service.get_workspace_vcs(
                initialization_strategy
            ).default_setup_command()
            if is_isolated_checkout(initialization_strategy)
            else None
            for initialization_strategy in WorkspaceInitializationStrategy
        }
    )


def _get_project(services: CompleteServiceCollection, user_session: UserSession, project_id: ProjectID) -> Project:
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_colocation(services: CompleteServiceCollection, project: Project) -> None:
    try:
        services.project_jj_state_service.require_colocation(project)
    except JjUnavailableForRepositoryError as e:
        raise HTTPException(status_code=412, detail=str(e)) from e
    except RepositoryNotColocatedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
