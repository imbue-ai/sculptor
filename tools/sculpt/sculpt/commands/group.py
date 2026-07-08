"""Commands for managing workspace groups (an experimental Sculptor feature).

Groups collect workspaces of one repo under a named, colored sidebar card.
Every command here expresses explicit group intent, so a disabled
workspace-groups experiment surfaces the backend's 409 error instead of
degrading silently (see ``_group_helpers``).
"""

import json
from http import HTTPStatus

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client import Client
from sculpt.client.api.default import create_workspace_group
from sculpt.client.api.default import list_recent_workspaces
from sculpt.client.api.default import remove_workspace_group_member
from sculpt.client.api.default import ungroup_workspace_group
from sculpt.client.api.default import update_workspace_group
from sculpt.client.models.create_workspace_group_request import CreateWorkspaceGroupRequest
from sculpt.client.models.recent_workspace_response import RecentWorkspaceResponse
from sculpt.client.models.update_workspace_group_request import UpdateWorkspaceGroupRequest
from sculpt.client.models.workspace_group_response import WorkspaceGroupResponse
from sculpt.commands._group_helpers import add_workspace_to_group
from sculpt.commands._group_helpers import fetch_groups
from sculpt.commands._group_helpers import raise_for_group_error
from sculpt.commands._group_helpers import resolve_group
from sculpt.commands.data_types import GroupAddOutput
from sculpt.commands.data_types import GroupCreateOutput
from sculpt.commands.data_types import GroupListItem
from sculpt.commands.data_types import GroupRemoveOutput
from sculpt.commands.data_types import GroupRenameOutput
from sculpt.commands.data_types import GroupShowOutput
from sculpt.commands.data_types import GroupUngroupOutput
from sculpt.formatting import cli_error
from sculpt.formatting import format_datetime
from sculpt.formatting import format_table
from sculpt.formatting import handle_connection_error
from sculpt.formatting import truncate
from sculpt.resolve import resolve_by_prefix
from sculpt.resolve import resolve_project

group_app = typer.Typer(
    name="group",
    help="Manage workspace groups (experimental; enable workspace groups in Settings).",
)

_NAME_DISPLAY_MAX_LENGTH = 30


def _fetch_recent_workspaces(client: Client, json_output: bool) -> list[RecentWorkspaceResponse]:
    try:
        result = list_recent_workspaces.sync(client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to list workspaces", detail="No response from server", json_output=json_output)

    return result.workspaces


def _resolve_member_workspaces(
    client: Client, workspace_refs: list[str], json_output: bool
) -> list[RecentWorkspaceResponse]:
    """Resolve workspace ID prefixes to workspaces, deduplicated in input order."""
    workspaces = _fetch_recent_workspaces(client, json_output)
    resolved: dict[str, RecentWorkspaceResponse] = {}
    for ref in workspace_refs:
        ws = resolve_by_prefix(ref, workspaces, lambda w: w.object_id)
        resolved[ws.object_id] = ws
    return list(resolved.values())


@group_app.command("create")
def create(
    workspace: list[str] = typer.Option(
        ...,
        "--workspace",
        "-w",
        help="Initial member workspace ID or prefix (repeatable; at least one is required)",
    ),
    name: str | None = typer.Option(None, "--name", help="Group name (server-assigned if omitted)"),
    color: str | None = typer.Option(
        None,
        "--color",
        help="Radix accent color name, e.g. blue, green, orange (server-assigned if omitted)",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Path to the repository. If omitted, inferred from the member workspaces.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Create a workspace group around one or more member workspaces."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    members = _resolve_member_workspaces(client, workspace, json_output)

    if repo is not None:
        project_id = resolve_project(repo, client)
    else:
        member_project_ids = {ws.project_id for ws in members}
        if len(member_project_ids) > 1:
            cli_error(
                "Member workspaces belong to different repos",
                detail="A group can only contain workspaces of one repo: "
                + ", ".join(f"{ws.object_id} ({ws.project_id})" for ws in members),
                json_output=json_output,
            )
        project_id = next(iter(member_project_ids))

    mismatched = [ws.object_id for ws in members if ws.project_id != project_id]
    if mismatched:
        cli_error(
            "All member workspaces must belong to the group's repo",
            detail=f"Not in {project_id}: {', '.join(mismatched)}",
            json_output=json_output,
        )

    # Groups created through this command carry the CLI badge in the sidebar.
    request = CreateWorkspaceGroupRequest(
        project_id=project_id,
        workspace_ids=[ws.object_id for ws in members],
        name=name,
        color=color,
        created_via_cli=True,
    )

    try:
        response = create_workspace_group.sync_detailed(client=client, body=request)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code != HTTPStatus.OK or not isinstance(response.parsed, WorkspaceGroupResponse):
        raise_for_group_error(response, action="create workspace group", json_output=json_output)
    group = response.parsed

    if json_output:
        output = GroupCreateOutput(
            id=group.object_id,
            repo_id=group.project_id,
            name=group.name,
            color=group.color,
            created_via_cli=group.created_via_cli,
            created_at=group.created_at.isoformat(),
            workspace_ids=group.workspace_ids,
        )
        typer.echo(output.model_dump_json(indent=2))
        return

    typer.echo(f"Group created: {group.object_id}")
    typer.echo(f"Name: {group.name}")
    typer.echo(f"Color: {group.color}")
    typer.echo(f"Repo: {group.project_id}")
    typer.echo(f"Workspaces: {', '.join(group.workspace_ids)}")


@group_app.command("list")
def list_cmd(
    repo: str | None = typer.Option(
        None,
        "--repo",
        help=(
            "Path to the repository. If omitted, the project is taken from the"
            + " SCULPT_PROJECT_ID env var (set in every Sculptor workspace shell),"
            + " or matched against the current working directory."
        ),
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """List the repo's workspace groups."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)
    project_id = resolve_project(repo, client)

    groups = fetch_groups(client, project_id=project_id, json_output=json_output)

    if json_output:
        items = [
            GroupListItem(
                id=g.object_id,
                repo_id=g.project_id,
                name=g.name,
                color=g.color,
                created_via_cli=g.created_via_cli,
                created_at=g.created_at.isoformat(),
                workspace_ids=g.workspace_ids,
            )
            for g in groups
        ]
        typer.echo(json.dumps([item.model_dump() for item in items], indent=2))
        return

    if not groups:
        typer.echo("No workspace groups found.")
        return

    headers = ["ID", "NAME", "COLOR", "WORKSPACES", "CLI"]
    rows = [
        [
            g.object_id,
            truncate(g.name, _NAME_DISPLAY_MAX_LENGTH),
            g.color,
            str(len(g.workspace_ids)),
            "yes" if g.created_via_cli else "-",
        ]
        for g in groups
    ]
    typer.echo(format_table(headers, rows))


@group_app.command("show")
def show(
    group_id: str = typer.Argument(..., help="Group ID or prefix"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Show details of a workspace group."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    group = resolve_group(client, group_id, json_output=json_output)

    if json_output:
        output = GroupShowOutput(
            id=group.object_id,
            repo_id=group.project_id,
            name=group.name,
            color=group.color,
            created_via_cli=group.created_via_cli,
            created_at=group.created_at.isoformat(),
            workspace_ids=group.workspace_ids,
        )
        typer.echo(output.model_dump_json(indent=2))
        return

    lines = [
        f"Group: {group.object_id}",
        f"Name: {group.name}",
        f"Color: {group.color}",
        f"Repo: {group.project_id}",
        f"Created via CLI: {'yes' if group.created_via_cli else 'no'}",
        f"Created: {format_datetime(group.created_at)}",
        f"Workspaces: {', '.join(group.workspace_ids)}",
    ]
    typer.echo("\n".join(lines))


@group_app.command("rename")
def rename(
    group_id: str = typer.Argument(..., help="Group ID or prefix"),
    name: str = typer.Argument(..., help="New name for the group"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Rename a workspace group."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    group = resolve_group(client, group_id, json_output=json_output)

    request = UpdateWorkspaceGroupRequest(name=name)
    try:
        response = update_workspace_group.sync_detailed(group_id=group.object_id, client=client, body=request)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code != HTTPStatus.OK or not isinstance(response.parsed, WorkspaceGroupResponse):
        raise_for_group_error(response, action="rename workspace group", json_output=json_output)
    renamed = response.parsed

    if json_output:
        output = GroupRenameOutput(id=renamed.object_id, name=renamed.name)
        typer.echo(output.model_dump_json())
        return

    typer.echo(f"Group {renamed.object_id} renamed to '{renamed.name}'.")


@group_app.command("add")
def add(
    group_id: str = typer.Argument(..., help="Group ID or prefix"),
    workspace_id: str = typer.Argument(..., help="Workspace ID or prefix to add"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Add a workspace to a group (moving it out of its previous group, if any)."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    group = resolve_group(client, group_id, json_output=json_output)

    workspaces = _fetch_recent_workspaces(client, json_output)
    ws = resolve_by_prefix(workspace_id, workspaces, lambda w: w.object_id)
    if ws.project_id != group.project_id:
        cli_error(
            "Workspace and group belong to different repos",
            detail=f"{ws.object_id} is in {ws.project_id}, but group {group.object_id} is in {group.project_id}",
            json_output=json_output,
        )

    updated = add_workspace_to_group(
        client,
        group_id=group.object_id,
        workspace_id=ws.object_id,
        json_output=json_output,
    )

    if json_output:
        output = GroupAddOutput(
            group_id=updated.object_id,
            workspace_id=ws.object_id,
            workspace_ids=updated.workspace_ids,
        )
        typer.echo(output.model_dump_json(indent=2))
        return

    typer.echo(f"Workspace {ws.object_id} added to group {updated.object_id}.")


@group_app.command("remove")
def remove(
    group_id: str = typer.Argument(..., help="Group ID or prefix"),
    workspace_id: str = typer.Argument(..., help="Workspace ID or prefix to remove"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Remove a workspace from its group (the group dissolves if this empties it)."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    group = resolve_group(client, group_id, json_output=json_output)
    resolved_workspace_id = resolve_by_prefix(workspace_id, group.workspace_ids, lambda member_id: member_id)

    try:
        response = remove_workspace_group_member.sync_detailed(
            group_id=group.object_id, workspace_id=resolved_workspace_id, client=client
        )
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code != HTTPStatus.OK:
        raise_for_group_error(response, action="remove workspace from group", json_output=json_output)

    if json_output:
        output = GroupRemoveOutput(removed=True, group_id=group.object_id, workspace_id=resolved_workspace_id)
        typer.echo(output.model_dump_json())
        return

    typer.echo(f"Workspace {resolved_workspace_id} removed from group {group.object_id}.")
    if len(group.workspace_ids) == 1:
        typer.echo(f"Group {group.object_id} is now empty and was dissolved.")


@group_app.command("ungroup")
def ungroup(
    group_id: str = typer.Argument(..., help="Group ID or prefix"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Dissolve a group, releasing its workspaces back to the loose list.

    Never deletes workspaces — a group is purely an organizational container.
    """
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    group = resolve_group(client, group_id, json_output=json_output)

    try:
        response = ungroup_workspace_group.sync_detailed(group_id=group.object_id, client=client)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code != HTTPStatus.OK:
        raise_for_group_error(response, action="ungroup workspace group", json_output=json_output)

    if json_output:
        output = GroupUngroupOutput(
            ungrouped=True,
            id=group.object_id,
            released_workspace_ids=group.workspace_ids,
        )
        typer.echo(output.model_dump_json(indent=2))
        return

    typer.echo(f"Group {group.object_id} ungrouped; released {len(group.workspace_ids)} workspace(s).")
