import json

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client.api.default import create_workspace_v2
from sculpt.client.api.default import delete_workspace
from sculpt.client.api.default import list_recent_workspaces
from sculpt.client.api.default import list_workspaces
from sculpt.client.api.default import update_workspace
from sculpt.client.models.create_workspace_request_v2 import CreateWorkspaceRequestV2
from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.client.models.update_workspace_request import UpdateWorkspaceRequest
from sculpt.commands._workspace_helpers import STRATEGY_MAPPING
from sculpt.commands._workspace_helpers import resolve_requested_branch_name
from sculpt.commands._workspace_helpers import resolve_strategy
from sculpt.commands.data_types import WorkspaceCreateOutput
from sculpt.commands.data_types import WorkspaceDeleteOutput
from sculpt.commands.data_types import WorkspaceListItem
from sculpt.commands.data_types import WorkspaceListProjectItem
from sculpt.commands.data_types import WorkspaceRenameOutput
from sculpt.commands.data_types import WorkspaceShowOutput
from sculpt.formatting import cli_error
from sculpt.formatting import format_datetime
from sculpt.formatting import format_table
from sculpt.formatting import handle_connection_error
from sculpt.formatting import truncate
from sculpt.resolve import fetch_repo_path_lookup
from sculpt.resolve import resolve_by_prefix
from sculpt.resolve import resolve_project

workspace_app = typer.Typer(
    name="workspace",
    help="Manage workspaces.",
)


@workspace_app.command("create")
def create(
    repo: str | None = typer.Option(
        None,
        "--repo",
        help=(
            "Path to the repository. If omitted, the project is taken from the"
            + " SCULPT_PROJECT_ID env var (set in every Sculptor workspace shell),"
            + " or matched against the current working directory."
        ),
    ),
    strategy: str = typer.Option(
        "worktree",
        "--strategy",
        help=f"Initialization strategy ({', '.join(STRATEGY_MAPPING)})",
    ),
    branch: str | None = typer.Option(None, "--branch", help="Source branch"),
    branch_name: str | None = typer.Option(
        None,
        "--branch-name",
        help="New branch name (required for worktree; auto-generated if omitted)",
    ),
    target_branch: str | None = typer.Option(
        None,
        "--target-branch",
        help="Diff/merge target branch (auto-resolved from the repo if omitted)",
    ),
    name: str | None = typer.Option(None, "--name", help="Workspace description"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Create a new workspace."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)
    project_id = resolve_project(repo, client)

    strategy_enum = resolve_strategy(strategy, json_output=json_output)

    resolved_branch_name = resolve_requested_branch_name(
        client=client,
        project_id=project_id,
        strategy=strategy_enum,
        branch_name=branch_name,
        workspace_name=name,
        json_output=json_output,
    )

    request = CreateWorkspaceRequestV2(
        project_id=project_id,
        initialization_strategy=strategy_enum,
        source_branch=branch,
        description=name,
        requested_branch_name=resolved_branch_name,
        target_branch=target_branch,
    )

    try:
        result = create_workspace_v2.sync(client=client, body=request)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to create workspace", detail="No response from server", json_output=json_output)

    if isinstance(result, HTTPValidationError):
        cli_error("Validation error", detail=str(result), json_output=json_output)

    if json_output:
        output = WorkspaceCreateOutput(
            id=result.object_id,
            repo_id=result.project_id,
            description=result.description,
            strategy=result.initialization_strategy.value,
            source_branch=result.source_branch,
        )
        typer.echo(output.model_dump_json(indent=2))
        return

    typer.echo(f"Workspace created: {result.object_id}")
    typer.echo(f"Repo: {result.project_id}")
    typer.echo(f"Strategy: {result.initialization_strategy.value}")
    if result.source_branch:
        typer.echo(f"Branch: {result.source_branch}")
    if result.description:
        typer.echo(f"Description: {result.description}")


@workspace_app.command("list")
def list_cmd(
    show_all: bool = typer.Option(False, "--all", help="List workspaces across all repos"),
    repo: str | None = typer.Option(None, "--repo", help="Path to the repository"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """List workspaces."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    if show_all:
        _list_all(client, json_output)
    else:
        project_id = resolve_project(repo, client)
        _list_for_project(client, project_id, json_output)


def _list_all(client: object, json_output: bool) -> None:
    workspaces = _fetch_recent_workspaces(client, json_output)
    repo_lookup = fetch_repo_path_lookup(client)  # type: ignore[arg-type]

    if json_output:
        items = [
            WorkspaceListItem(
                id=w.object_id,
                repo_id=w.project_id,
                repo_path=repo_lookup.get(w.project_id, w.project_name),
                description=w.description,
                strategy=w.initialization_strategy.value,
                source_branch=w.source_branch,
                agent_count=w.agent_count,
                is_open=w.is_open,
                created_at=w.created_at.isoformat(),
                last_activity_at=w.last_activity_at.isoformat(),
            )
            for w in workspaces
        ]
        typer.echo(json.dumps([item.model_dump() for item in items], indent=2))
        return

    if not workspaces:
        typer.echo("No workspaces found.")
        return

    headers = ["ID", "REPO", "STRATEGY", "BRANCH", "AGENTS", "DESCRIPTION"]
    rows = [
        [
            w.object_id,
            truncate(repo_lookup.get(w.project_id, w.project_name), 30),
            w.initialization_strategy.value,
            w.source_branch or "-",
            str(w.agent_count),
            truncate(w.description, 30),
        ]
        for w in workspaces
    ]
    typer.echo(format_table(headers, rows))


def _fetch_recent_workspaces(client: object, json_output: bool) -> list:
    try:
        result = list_recent_workspaces.sync(client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to list workspaces", detail="No response from server", json_output=json_output)

    return result.workspaces


def _list_for_project(client: object, project_id: str, json_output: bool) -> None:
    try:
        result = list_workspaces.sync(project_id=project_id, client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to list workspaces", detail="No response from server", json_output=json_output)

    if isinstance(result, HTTPValidationError):
        cli_error("Validation error", detail=str(result), json_output=json_output)

    if json_output:
        items = [
            WorkspaceListProjectItem(
                id=w.object_id,
                repo_id=w.project_id,
                description=w.description,
                strategy=w.initialization_strategy.value,
                source_branch=w.source_branch,
                is_deleted=w.is_deleted,
            )
            for w in result
        ]
        typer.echo(json.dumps([item.model_dump() for item in items], indent=2))
        return

    if not result:
        typer.echo("No workspaces found.")
        return

    headers = ["ID", "STRATEGY", "BRANCH", "DESCRIPTION"]
    rows = [
        [
            w.object_id,
            w.initialization_strategy.value,
            w.source_branch or "-",
            truncate(w.description, 40),
        ]
        for w in result
    ]
    typer.echo(format_table(headers, rows))


@workspace_app.command("show")
def show(
    workspace_id: str = typer.Argument(..., help="Workspace ID or prefix"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Show details of a workspace."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    workspaces = _fetch_recent_workspaces(client, json_output)
    ws = resolve_by_prefix(workspace_id, workspaces, lambda w: w.object_id)

    repo_lookup = fetch_repo_path_lookup(client)  # type: ignore[arg-type]
    repo_path = repo_lookup.get(ws.project_id, ws.project_name)

    if json_output:
        output = WorkspaceShowOutput(
            id=ws.object_id,
            repo_id=ws.project_id,
            repo_path=repo_path,
            description=ws.description,
            strategy=ws.initialization_strategy.value,
            source_branch=ws.source_branch,
            agent_count=ws.agent_count,
            is_open=ws.is_open,
            created_at=ws.created_at.isoformat(),
            last_activity_at=ws.last_activity_at.isoformat(),
        )
        typer.echo(output.model_dump_json(indent=2))
        return

    lines = [
        f"Workspace: {ws.object_id}",
        f"Repo: {repo_path} ({ws.project_id})",
        f"Strategy: {ws.initialization_strategy.value}",
        f"Branch: {ws.source_branch or '-'}",
        f"Description: {ws.description}",
        f"Created: {format_datetime(ws.created_at)}",
        f"Agents: {ws.agent_count}",
        f"Last Activity: {format_datetime(ws.last_activity_at)}",
    ]
    typer.echo("\n".join(lines))


@workspace_app.command("rename")
def rename(
    workspace_id: str = typer.Argument(..., help="Workspace ID or prefix"),
    description: str = typer.Argument(..., help="New description for the workspace"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Rename a workspace (update its description)."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    workspaces = _fetch_recent_workspaces(client, json_output)
    ws = resolve_by_prefix(workspace_id, workspaces, lambda w: w.object_id)
    resolved_id = ws.object_id

    request = UpdateWorkspaceRequest(description=description)

    try:
        result = update_workspace.sync(workspace_id=resolved_id, client=client, body=request)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to rename workspace", detail="No response from server", json_output=json_output)

    if isinstance(result, HTTPValidationError):
        cli_error("Validation error", detail=str(result), json_output=json_output)

    if json_output:
        output = WorkspaceRenameOutput(id=resolved_id, description=description)
        typer.echo(output.model_dump_json())
        return

    typer.echo(f"Workspace {resolved_id} renamed to '{description}'.")


@workspace_app.command("delete")
def delete(
    workspace_id: str = typer.Argument(..., help="Workspace ID or prefix"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Delete a workspace and all its agents."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)

    workspaces = _fetch_recent_workspaces(client, json_output)
    ws = resolve_by_prefix(workspace_id, workspaces, lambda w: w.object_id)
    resolved_id = ws.object_id

    if not yes:
        typer.confirm(f"Delete workspace {resolved_id}?", abort=True)

    try:
        delete_workspace.sync(workspace_id=resolved_id, client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if json_output:
        output = WorkspaceDeleteOutput(deleted=True, id=resolved_id)
        typer.echo(output.model_dump_json())
        return

    typer.echo(f"Workspace {resolved_id} deleted.")
