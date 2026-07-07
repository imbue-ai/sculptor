import datetime
import json

import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client.models.project import Project
from sculpt.commands.data_types import RepoItem
from sculpt.formatting import format_datetime
from sculpt.formatting import format_table
from sculpt.formatting import truncate
from sculpt.resolve import fetch_projects
from sculpt.resolve import repo_path_from_url
from sculpt.resolve import resolve_by_prefix

_NAME_DISPLAY_MAX_LENGTH = 20
_PATH_DISPLAY_MAX_LENGTH = 50

repo_app = typer.Typer(
    name="repo",
    help="Manage repos.",
)


def _repo_item_from_project(project: Project) -> RepoItem:
    """Build the JSON output model for a single repo from a project."""
    created_at = (
        project.created_at.isoformat() if isinstance(project.created_at, datetime.datetime) else None
    )
    return RepoItem(
        id=project.object_id,
        name=project.name,
        path=repo_path_from_url(project.user_git_repo_url),
        accessible=project.is_path_accessible,
        created_at=created_at,
    )


@repo_app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """List all known repos."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)
    projects = fetch_projects(client, json_output)

    if json_output:
        items = [_repo_item_from_project(p) for p in projects]
        typer.echo(json.dumps([item.model_dump() for item in items], indent=2))
        return

    if not projects:
        typer.echo("No repos found.")
        return

    headers = ["ID", "NAME", "PATH", "ACCESSIBLE"]
    rows = [
        [
            p.object_id,
            truncate(p.name, _NAME_DISPLAY_MAX_LENGTH),
            truncate(repo_path_from_url(p.user_git_repo_url), _PATH_DISPLAY_MAX_LENGTH),
            "yes" if p.is_path_accessible else "no",
        ]
        for p in projects
    ]
    typer.echo(format_table(headers, rows))


@repo_app.command("show")
def show(
    repo_id: str = typer.Argument(..., help="Repo ID or prefix"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Show details of a repo."""
    base_url = base_url or get_default_base_url()
    client = get_authenticated_client(base_url)
    projects = fetch_projects(client, json_output)

    project = resolve_by_prefix(
        repo_id,
        projects,
        lambda p: p.object_id,
        resource_noun="repo",
        json_output=json_output,
        label_getter=lambda p: p.name,
    )

    if json_output:
        typer.echo(_repo_item_from_project(project).model_dump_json(indent=2))
        return

    path = repo_path_from_url(project.user_git_repo_url)
    lines = [
        f"Repo: {project.object_id}",
        f"Name: {project.name}",
        f"Path: {path}",
        f"Accessible: {'yes' if project.is_path_accessible else 'no'}",
    ]
    if isinstance(project.created_at, datetime.datetime):
        lines.append(f"Created: {format_datetime(project.created_at)}")
    typer.echo("\n".join(lines))
