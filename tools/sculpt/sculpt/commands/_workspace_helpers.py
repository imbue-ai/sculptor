"""Shared helpers for workspace-creating commands (``sculpt workspace create`` and ``sculpt run``)."""

from typing import assert_never

import httpx

from sculpt.client import Client
from sculpt.client.api.default import create_workspace_v2
from sculpt.client.api.default import preview_branch_name
from sculpt.client.models.create_workspace_request_v2 import CreateWorkspaceRequestV2
from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.client.models.workspace_initialization_strategy import WorkspaceInitializationStrategy
from sculpt.client.models.workspace_response import WorkspaceResponse
from sculpt.formatting import cli_error
from sculpt.formatting import extract_error_detail
from sculpt.formatting import handle_connection_error


def _strategy_option_name(strategy: WorkspaceInitializationStrategy) -> str:
    """The ``--strategy`` value that selects ``strategy``."""
    match strategy:
        case WorkspaceInitializationStrategy.CLONE:
            return "clone"
        case WorkspaceInitializationStrategy.IN_PLACE:
            return "in-place"
        case WorkspaceInitializationStrategy.WORKTREE:
            return "worktree"
        case WorkspaceInitializationStrategy.JJ_WORKSPACE:
            return "jj"
        case _ as unreachable:
            assert_never(unreachable)


STRATEGY_MAPPING = {_strategy_option_name(strategy): strategy for strategy in WorkspaceInitializationStrategy}


def resolve_strategy(strategy: str, json_output: bool) -> WorkspaceInitializationStrategy:
    """Validate ``--strategy`` and return the matching enum, or exit with a clean error."""
    strategy_lower = strategy.lower()
    if strategy_lower not in STRATEGY_MAPPING:
        valid = ", ".join(STRATEGY_MAPPING)
        cli_error(f"Invalid strategy '{strategy}'. Valid options: {valid}", json_output=json_output)
    return STRATEGY_MAPPING[strategy_lower]


def resolve_requested_branch_name(
    *,
    client: Client,
    project_id: str,
    strategy: WorkspaceInitializationStrategy,
    branch_name: str | None,
    workspace_name: str | None,
    json_output: bool,
) -> str | None:
    """Resolve ``requested_branch_name`` to send when creating a workspace.

    For WORKTREE, or JJ_WORKSPACE (whose name is its bookmark's), without an
    explicit ``--branch-name``, mirror the UI by calling
    ``/api/v1/workspaces/preview-branch-name`` to auto-fill a slug derived
    from the workspace name (or a random one if no name was given). For other
    strategies, pass the user's value through untouched and let the backend
    validate.
    """
    if branch_name is not None:
        return branch_name
    match strategy:
        case WorkspaceInitializationStrategy.WORKTREE | WorkspaceInitializationStrategy.JJ_WORKSPACE:
            return _preview_branch_name(
                client=client,
                project_id=project_id,
                strategy=strategy,
                workspace_name=workspace_name,
                json_output=json_output,
            )
        case WorkspaceInitializationStrategy.CLONE | WorkspaceInitializationStrategy.IN_PLACE:
            return None
        case _ as unreachable:
            assert_never(unreachable)


def _preview_branch_name(
    *,
    client: Client,
    project_id: str,
    strategy: WorkspaceInitializationStrategy,
    workspace_name: str | None,
    json_output: bool,
) -> str:
    try:
        preview = preview_branch_name.sync(
            client=client,
            project_id=project_id,
            workspace_name=workspace_name or "",
            mode=strategy,
        )
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if preview is None:
        cli_error(
            f"Failed to resolve branch name for {strategy} workspace",
            detail="No response from server",
            json_output=json_output,
        )
    if isinstance(preview, HTTPValidationError):
        cli_error("Validation error resolving branch name", detail=str(preview), json_output=json_output)
    return preview.branch_name


def create_workspace_or_exit(
    *, client: Client, request: CreateWorkspaceRequestV2, json_output: bool
) -> WorkspaceResponse:
    """Create the workspace `request` describes, or exit with the reason the server gave for refusing it."""
    try:
        response = create_workspace_v2.sync_detailed(client=client, body=request)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    result = response.parsed
    if isinstance(result, HTTPValidationError):
        cli_error("Validation error", detail=str(result), json_output=json_output)

    if result is None:
        cli_error(
            "Failed to create workspace",
            detail=extract_error_detail(response.content)
            or f"Unexpected response from server (status {response.status_code})",
            json_output=json_output,
        )
    return result
