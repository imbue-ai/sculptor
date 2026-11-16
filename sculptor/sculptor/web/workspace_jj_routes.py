"""Routes that serve a jj workspace's own data, which has no git equivalent."""

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from sculptor.services.jj_availability import JjUnavailableError
from sculptor.services.workspace_service.api import WorkspaceNotFoundError
from sculptor.services.workspace_service.api import WorkspaceRevisionHistoryUnavailableError
from sculptor.services.workspace_service.api import WorkspaceWorkingCopyUpdateUnavailableError
from sculptor.services.workspace_service.vcs.errors import JjWorkingCopyStaleError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.jj_data_types import JjRevisionRecord
from sculptor.web.auth import UserSession
from sculptor.web.data_types import CommitFileInfo
from sculptor.web.data_types import RevisionHistoryResponse
from sculptor.web.data_types import RevisionInfo
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_services_from_request_or_websocket
from sculptor.web.middleware import get_user_session
from sculptor.web.path_id_validation import validate_workspace_id

workspace_jj_router = DecoratedAPIRouter(decorator=add_logging_context)


@workspace_jj_router.get("/api/v1/workspaces/{workspace_id}/revisions")
def get_workspace_revisions(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> RevisionHistoryResponse:
    """A jj workspace's revisions, newest first, back to where its stack forks from its target.

    Answers 409 for a git workspace, whose history is served by the commits route,
    and for a jj workspace whose working copy is stale, which the user updates first.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
        try:
            history = services.workspace_service.get_revision_history(validated_workspace_id, transaction)
        except WorkspaceNotFoundError:
            return RevisionHistoryResponse(revisions=[], fork_point=None)
        except WorkspaceRevisionHistoryUnavailableError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except JjWorkingCopyStaleError as e:
            raise HTTPException(
                status_code=409, detail=f"The working copy of workspace {workspace_id} is stale; update it first"
            ) from e

    return RevisionHistoryResponse(
        revisions=[_to_revision_info(record) for record in history.revisions], fork_point=history.fork_point
    )


def _to_revision_info(record: JjRevisionRecord) -> RevisionInfo:
    return RevisionInfo(
        change_id=record.change_id,
        change_id_prefix_length=len(record.change_id_prefix),
        commit_id=record.commit_id,
        description=record.description,
        author_name=record.author_name,
        timestamp=record.timestamp,
        parent_commit_ids=list(record.parent_commit_ids),
        files=[
            CommitFileInfo(
                path=file.path,
                status=file.status,
                old_path=file.old_path,
                additions=file.additions,
                deletions=file.deletions,
            )
            for file in record.files
        ],
        bookmarks=list(record.bookmarks),
        is_working_copy=record.is_working_copy,
        is_empty=record.is_empty,
        has_conflict=record.has_conflict,
        is_divergent=record.is_divergent,
    )


@workspace_jj_router.post("/api/v1/workspaces/{workspace_id}/jj/update-stale", status_code=204)
def update_stale_working_copy(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Bring a jj workspace's stale working copy up to date with its repository, on the user's request.

    Answers 412 while jj is unavailable, and 409 for a git workspace and when jj cannot update the working copy.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
        try:
            services.workspace_service.update_stale_working_copy(validated_workspace_id, transaction)
        except WorkspaceNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except JjUnavailableError as e:
            raise HTTPException(status_code=412, detail=str(e)) from e
        except (WorkspaceWorkingCopyUpdateUnavailableError, VcsCommandError) as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
