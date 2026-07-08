"""Shared workspace-group helpers for the sculpt CLI.

Workspace groups are gated behind an experimental flag; while it is off the
backend rejects every group endpoint with HTTP 409 and the stable error code
``workspace_groups_disabled``. Commands expressing *explicit* group intent
(``sculpt group *``, ``--group``) surface that error loudly, while the
*implicit* auto-group step in ``sculpt run`` / ``sculpt workspace create``
catches it and proceeds without a group. Both paths funnel through here so
the detection logic lives in one place.
"""

import json
from http import HTTPStatus
from typing import NoReturn

import httpx
import typer

from sculpt.client import Client
from sculpt.client.api.default import add_workspace_group_member
from sculpt.client.api.default import create_workspace_group
from sculpt.client.api.default import list_workspace_groups
from sculpt.client.models.add_workspace_group_member_request import AddWorkspaceGroupMemberRequest
from sculpt.client.models.create_workspace_group_request import CreateWorkspaceGroupRequest
from sculpt.client.models.list_workspace_groups_response import ListWorkspaceGroupsResponse
from sculpt.client.models.workspace_group_response import WorkspaceGroupResponse
from sculpt.client.types import Response
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error
from sculpt.resolve import resolve_by_prefix

# Stable error code the backend returns (HTTP 409) for every group endpoint
# while the workspace-groups experiment is disabled.
WORKSPACE_GROUPS_DISABLED_CODE = "workspace_groups_disabled"

_ENABLE_HINT = "Workspace groups are an experimental feature; enable them in Settings first."


def extract_structured_error(content: bytes) -> tuple[str | None, str]:
    """Pull (code, message) out of a FastAPI error response body.

    The backend raises group errors either with a structured dict detail
    ``{"error": <code>, "message": <text>}`` or with a plain string detail.
    Returns ``(None, "")`` when the body has neither.
    """
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return None, ""
    if not isinstance(parsed, dict):
        return None, ""
    detail = parsed.get("detail")
    if isinstance(detail, dict):
        code = detail.get("error")
        message = detail.get("message")
        return (
            code if isinstance(code, str) else None,
            message if isinstance(message, str) else "",
        )
    if isinstance(detail, str):
        return None, detail
    return None, ""


def raise_for_group_error(response: Response, *, action: str, json_output: bool) -> NoReturn:
    """Exit with a group-endpoint error, keyed to the backend's structured detail.

    The disabled-experiment 409 gets a dedicated message (and machine-readable
    ``code`` in JSON mode) directing the user to Settings; everything else
    surfaces the backend detail verbatim.
    """
    code, message = extract_structured_error(response.content)
    if response.status_code == HTTPStatus.CONFLICT and code == WORKSPACE_GROUPS_DISABLED_CODE:
        cli_error(
            "Workspace groups are disabled",
            detail=message or _ENABLE_HINT,
            code=WORKSPACE_GROUPS_DISABLED_CODE,
            json_output=json_output,
        )
    cli_error(
        f"Failed to {action}",
        detail=message or f"Server returned status {response.status_code}",
        json_output=json_output,
    )


def fetch_groups(client: Client, *, project_id: str | None, json_output: bool) -> list[WorkspaceGroupResponse]:
    """List live workspace groups, optionally scoped to a project.

    This is an explicit-intent call: a disabled experiment (or any other
    failure) errors out rather than degrading.
    """
    try:
        response = list_workspace_groups.sync_detailed(client=client, project_id=project_id)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code != HTTPStatus.OK or not isinstance(response.parsed, ListWorkspaceGroupsResponse):
        raise_for_group_error(response, action="list workspace groups", json_output=json_output)
    return response.parsed.groups


def resolve_group(client: Client, group_id_or_prefix: str, *, json_output: bool) -> WorkspaceGroupResponse:
    """Resolve a group ID prefix to the full group, across all projects."""
    groups = fetch_groups(client, project_id=None, json_output=json_output)
    return resolve_by_prefix(group_id_or_prefix, groups, lambda g: g.object_id)


def resolve_group_for_join(
    client: Client,
    group_id_or_prefix: str,
    *,
    project_id: str,
    json_output: bool,
) -> WorkspaceGroupResponse:
    """Resolve a ``--group`` target before any workspace is created.

    Failing here (unknown group, wrong repo, disabled experiment) leaves no
    side effects, whereas failing after workspace creation would strand a
    fresh workspace outside the requested group.
    """
    group = resolve_group(client, group_id_or_prefix, json_output=json_output)
    if group.project_id != project_id:
        cli_error(
            "Group belongs to a different repo",
            detail=f"Group {group.object_id} is in {group.project_id}, not {project_id}",
            json_output=json_output,
        )
    return group


def add_workspace_to_group(
    client: Client,
    *,
    group_id: str,
    workspace_id: str,
    json_output: bool,
) -> WorkspaceGroupResponse:
    """Add a workspace to an existing group, erroring loudly on any failure."""
    request = AddWorkspaceGroupMemberRequest(workspace_id=workspace_id)
    try:
        response = add_workspace_group_member.sync_detailed(group_id=group_id, client=client, body=request)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code != HTTPStatus.OK or not isinstance(response.parsed, WorkspaceGroupResponse):
        raise_for_group_error(response, action="add workspace to group", json_output=json_output)
    return response.parsed


def create_group_for_new_workspace(
    client: Client,
    *,
    project_id: str,
    workspace_id: str,
    json_output: bool,
) -> str | None:
    """Auto-group a freshly created CLI workspace, returning the new group's ID.

    This is the *implicit* grouping path: when the workspace-groups experiment
    is disabled the workspace simply stays loose (returning None, with a
    one-line stderr note in text mode). Any other failure still errors loudly.
    """
    request = CreateWorkspaceGroupRequest(
        project_id=project_id,
        workspace_ids=[workspace_id],
        created_via_cli=True,
    )
    try:
        response = create_workspace_group.sync_detailed(client=client, body=request)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code == HTTPStatus.OK and isinstance(response.parsed, WorkspaceGroupResponse):
        return response.parsed.object_id

    code, _ = extract_structured_error(response.content)
    if response.status_code == HTTPStatus.CONFLICT and code == WORKSPACE_GROUPS_DISABLED_CODE:
        if not json_output:
            typer.echo(
                "Note: the workspace-groups experiment is disabled; the workspace was created ungrouped.",
                err=True,
            )
        return None

    raise_for_group_error(response, action="auto-create workspace group", json_output=json_output)
